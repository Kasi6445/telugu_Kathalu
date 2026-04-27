"""
lib/image_gen.py — Image generation for Telugu Katalu.

Approach A (primary): Gemini Flash image generation via AI Studio.
  Scene 1 : text-only prompt establishes the visual look.
  Scenes 2-N: scene 1 passed as reference image for character consistency.

Approach C (fallback): Imagen on Vertex (ADC auth), no reference support.
  Activated when ALL Gemini models are inaccessible, OR when scene 1
  fell back to Imagen (mixing models breaks style across scenes).
  Consistency maintained by repeating the verbatim scene-1 character
  description as a locked anchor in every subsequent scene's prompt.

Model discovery: _get_working_gemini_model() probes _GEMINI_IMAGE_MODELS
  in order, caches the first accessible model, reuses it for the session.

Pacing  : SCENE_SLEEP (70s) between every scene — guaranteed under 1/min quota.
Retry   : 429 → 70s → retry → 120s → retry → 300s → retry → RuntimeError.
Lineage : drafts/{id}/image_lineage.json records which generator produced each scene.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from lib.config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_API_KEY, STYLE_LOCK

logger = logging.getLogger(__name__)

# ── Model cascade ─────────────────────────────────────────────────────────────

# Approach A: Gemini image generation — tried in order, first accessible wins.
_GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-preview-image-generation",
    "gemini-2.0-flash-exp",
]

# Approach C fallback: Imagen on Vertex.
_IMAGEN_MODELS = [
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-3.0-generate-002",
]

# ── Timing ────────────────────────────────────────────────────────────────────

SCENE_SLEEP  = 70              # mandatory seconds between scene generations
_RETRY_WAITS = [70, 120, 300]  # escalating waits on 429 — 3 retries total

# ── Session cache for Gemini model discovery ──────────────────────────────────

_cached_gemini_model: str | None = None   # None = not yet probed OR none found
_gemini_probe_done: bool = False          # True once discovery is complete


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SceneImageResult:
    scene_id:  int
    path:      Path
    generator: str   # "gemini" | "imagen"
    success:   bool


# ── Client helpers ────────────────────────────────────────────────────────────

def _gemini_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _vertex_client() -> genai.Client:
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)


# ── Gemini model discovery ────────────────────────────────────────────────────

def _get_working_gemini_model() -> str | None:
    """
    Probe _GEMINI_IMAGE_MODELS in order. Cache and return the first accessible one.
    A model is 'accessible' if it responds with a generated image OR returns 429
    (quota-limited, but the model exists and is reachable).
    Any other error (404, permission denied, unknown model) → try next model.
    Returns None if no Gemini image model is available — caller uses Imagen for all scenes.
    """
    global _cached_gemini_model, _gemini_probe_done

    if _gemini_probe_done:
        return _cached_gemini_model

    _gemini_probe_done = True   # set before probing — avoids re-entry on concurrent calls

    client = _gemini_client()
    probe_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )

    for model in _GEMINI_IMAGE_MODELS:
        try:
            logger.info(f"[IMAGE MODEL] Probing {model}...")
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part(text="A simple red circle on white background.")],
                config=probe_config,
            )
            # If we reach here, the model responded — check for image data
            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    _cached_gemini_model = model
                    logger.info(f"[IMAGE MODEL] Using {model}")
                    print(f"[IMAGE MODEL] Using {model}", flush=True)
                    return _cached_gemini_model

            # Model responded but returned no image data — try next
            logger.warning(f"[IMAGE MODEL] {model} responded but returned no image data — trying next")

        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                # Model is accessible — quota-limited on probe, but it works
                _cached_gemini_model = model
                logger.info(f"[IMAGE MODEL] Using {model} (quota-limited on probe — model is accessible)")
                print(f"[IMAGE MODEL] Using {model}", flush=True)
                return _cached_gemini_model
            # Not found / not available / permission error → try next
            logger.warning(
                f"[IMAGE MODEL] {model} not accessible: "
                f"{exc.__class__.__name__}: {str(exc)[:120]} — trying next"
            )

    # No Gemini model worked
    _cached_gemini_model = None
    logger.warning("[IMAGE MODEL] No Gemini image model accessible — all scenes will use Imagen (Approach C)")
    print("[IMAGE MODEL] No Gemini image model accessible — using Imagen for all scenes", flush=True)
    return None


# ── Prompt construction ───────────────────────────────────────────────────────

_DIRECTOR_PREFIX = (
    "Children's picture book illustration for ages 5-10. "
    "Gentle, warm, peaceful tone. "
    "NO violence, NO aggressive poses, NO scary imagery, NO dark atmosphere. "
    "CHARACTER COUNT RULE — CRITICAL: Show EXACTLY ONE instance of the main character. "
    "NEVER place two or more copies of the same person in the same scene. "
    "If a second character appears, they MUST look completely different: "
    "different clothing colour, different face, different body type. "
    "When in doubt, show only the main character. "
)


def _build_prompt(scene: dict, story: dict) -> str:
    """
    5-layer prompt with character/setting FIRST so the model weights them highest.

    Layer 1 (CHARACTER): verbatim main_character description with visual anchors.
    Layer 2 (SETTING)  : verbatim setting description with visual anchors.
    Layer 3 (SCENE)    : the specific moment, action, emotion from image_prompt.
    Layer 4 (STYLE)    : locked art direction.

    Prefixed with the director framing.
    """
    return (
        f"{_DIRECTOR_PREFIX}"
        f"CHARACTER: {story['main_character']} "
        f"SETTING: {story['setting']} "
        f"SCENE: {scene.get('image_prompt', '')} "
        f"{STYLE_LOCK}"
    )


def _build_gemini_reference_prompt(scene: dict, story: dict) -> str:
    """
    Prompt for Gemini scenes 2-N. Opens with explicit consistency instruction
    so the model treats the reference image as a hard constraint, not a suggestion.
    """
    base = _build_prompt(scene, story)
    return (
        "CONSISTENCY CONSTRAINT: The reference image shows scene 1 of this story. "
        "Maintain the EXACT same character appearance — same face structure, same clothing "
        "colors, same art style, same color palette, same brushwork. "
        "ONLY the background scene and character action may change. "
        "Do not invent new physical features. Do not change clothing. "
        + base
    )


def _build_imagen_consistency_prompt(scene: dict, story: dict) -> str:
    """
    Prompt for Imagen scenes 2-N (Approach C — no reference image available).
    Repeats the character description twice with an explicit 'LOCKED' label
    to push Imagen toward consistency without a visual reference.
    """
    base = _build_prompt(scene, story)
    return (
        "LOCKED CHARACTER — do not deviate from this description under any circumstances: "
        f"{story['main_character']} "
        "This is the same character who appeared in the opening scene. "
        "Every physical feature, clothing item, and color must match exactly. "
        + base
    )


# ── Low-level API calls ───────────────────────────────────────────────────────

def _call_gemini_generate(prompt: str, output_path: Path,
                           reference_path: Path | None,
                           model: str) -> bool:
    """
    One Gemini generate_content call.
    Returns True if image was saved.
    Raises on any API error — caller classifies (quota vs unavailable).
    """
    client = _gemini_client()

    if reference_path and reference_path.exists():
        image_bytes = reference_path.read_bytes()
        contents = [
            types.Part(inline_data=types.Blob(data=image_bytes, mime_type="image/png")),
            types.Part(text=prompt),
        ]
    else:
        contents = [types.Part(text=prompt)]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(part.inline_data.data)
            logger.info(f"Gemini image saved: {output_path.name} via {model}")
            return True

    return False   # response came back but no image part


def _call_imagen_generate(prompt: str, output_path: Path) -> bool:
    """
    Imagen cascade on Vertex: tries each model until one succeeds.
    Returns True if image was saved.
    Re-raises 429 — caller handles retry.
    Raises RuntimeError if all Imagen models fail with non-quota errors.
    """
    client = _vertex_client()
    cfg = types.GenerateImagesConfig(
        number_of_images=1,
        aspect_ratio="4:3",
        safety_filter_level="BLOCK_ONLY_HIGH",
        person_generation="ALLOW_ALL",   # children's story app — child characters must be allowed
    )

    last_exc: Exception | None = None

    for model in _IMAGEN_MODELS:
        try:
            logger.info(f"Imagen: trying {model} → {output_path.name}")
            resp = client.models.generate_images(model=model, prompt=prompt, config=cfg)

            # Guard: None or empty response (safety-blocked content returns empty list)
            if not resp or not resp.generated_images:
                logger.warning(f"Imagen {model} returned empty generated_images — safety-blocked? Trying next model.")
                last_exc = ValueError(f"{model}: generated_images empty or None")
                continue

            generated = resp.generated_images[0]
            if generated is None or generated.image is None:
                logger.warning(f"Imagen {model} returned null image object — trying next model.")
                last_exc = ValueError(f"{model}: image object is None")
                continue

            # Save: try raw bytes first, fall back to PIL .save()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img = generated.image
            try:
                raw = img.image_bytes   # raises ValueError if bytes are None (safety-blocked)
                output_path.write_bytes(raw)
            except (ValueError, AttributeError):
                # image_bytes not set — try PIL save (older response format)
                img.save(str(output_path))

            logger.info(f"Imagen image saved: {output_path.name} via {model}")
            return True

        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                raise   # quota error — caller handles escalating retry
            logger.warning(f"Imagen {model} failed: {exc.__class__.__name__}: {str(exc)[:120]}")
            last_exc = exc

    raise RuntimeError(
        f"All Imagen models failed for {output_path.name}. "
        f"Last error: {last_exc}"
    )


# ── Per-scene retry wrapper ───────────────────────────────────────────────────

def _generate_scene_image(
    prompt_gemini: str,
    prompt_imagen: str,
    output_path: Path,
    reference_path: Path | None,
    gemini_model: str | None,
    scene_label: str,
    logs_dir: Path,
) -> SceneImageResult:
    """
    Generate one scene image with escalating 429 retry.
    Retry ladder: 70s → 120s → 300s → RuntimeError (pipeline halt).

    prompt_gemini  : prompt used when calling Gemini (may include consistency prefix)
    prompt_imagen  : prompt used when calling Imagen (Approach C anchor wording)
    reference_path : set only for Gemini scenes 2-N; None otherwise
    gemini_model   : None means skip Gemini entirely (Approach C path for whole story)

    Returns SceneImageResult with generator="gemini"|"imagen".
    """
    retry_waits = list(_RETRY_WAITS)   # [70, 120, 300]

    # Determine starting approach
    use_gemini = gemini_model is not None

    for attempt in range(1, len(_RETRY_WAITS) + 2):   # attempts 1..4
        try:
            if use_gemini:
                success = _call_gemini_generate(prompt_gemini, output_path, reference_path, gemini_model)
                if success:
                    return SceneImageResult(
                        scene_id  = int(output_path.stem.replace("scene", "")),
                        path      = output_path,
                        generator = "gemini",
                        success   = True,
                    )
                # Gemini responded but returned no image — fall through to Imagen
                logger.warning(f"{scene_label} Gemini returned no image data — falling back to Imagen")
                use_gemini = False
                continue   # retry immediately with Imagen

            else:
                success = _call_imagen_generate(prompt_imagen, output_path)
                if success:
                    return SceneImageResult(
                        scene_id  = int(output_path.stem.replace("scene", "")),
                        path      = output_path,
                        generator = "imagen",
                        success   = True,
                    )

        except Exception as exc:
            err = str(exc)

            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if retry_waits:
                    wait = retry_waits.pop(0)
                    source = "Gemini" if use_gemini else "Imagen"
                    logger.warning(
                        f"{scene_label} 429 on {source} attempt {attempt} — "
                        f"sleeping {wait}s then retrying"
                    )
                    print(f"\n  ⏸  Rate limited ({source}). Waiting {wait}s...", flush=True)
                    time.sleep(wait)
                    # continue to next attempt (same source — quota may have cleared)
                else:
                    _append_failure_log(output_path, prompt_gemini if use_gemini else prompt_imagen,
                                        logs_dir, str(exc))
                    raise RuntimeError(
                        f"\n\nIMAGE GENERATION STUCK — {scene_label}\n"
                        f"  Rate limit (429) persisted through all retries "
                        f"(waited 70s + 120s + 300s).\n"
                        f"  Resolve quota manually, then re-run generate.py.\n"
                        f"  Partial draft NOT saved."
                    ) from exc

            elif use_gemini:
                # Non-quota Gemini error — fall back to Imagen for this scene
                logger.warning(
                    f"{scene_label} Gemini failed ({exc.__class__.__name__}: "
                    f"{str(exc)[:120]}) — falling back to Imagen"
                )
                use_gemini = False
                # don't consume a retry slot — Imagen is a different path
                continue

            else:
                _append_failure_log(output_path, prompt_imagen, logs_dir, str(exc))
                raise RuntimeError(
                    f"\n\nIMAGE GENERATION STUCK — {scene_label}\n"
                    f"  Imagen failed (non-quota): {exc}\n"
                    f"  Resolve manually, then re-run generate.py.\n"
                    f"  Partial draft NOT saved."
                ) from exc

    # Should not reach here — exhausted retries without raising
    raise RuntimeError(f"{scene_label} — retry loop exhausted without resolution. Partial draft NOT saved.")


def _append_failure_log(output_path: Path, prompt: str, logs_dir: Path, error: str):
    log_file = logs_dir / "image_failures.log"
    logs_dir.mkdir(exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            f"FAILED: {output_path}\n"
            f"ERROR:  {error}\n"
            f"PROMPT: {prompt[:400]}\n\n"
        )


# ── PNG → JPEG compression ───────────────────────────────────────────────────

def _compress_to_jpeg(images_path: Path, total: int,
                      quality: int = 82, max_width: int = 1024) -> None:
    """Convert all scene PNGs to JPEG after generation.
    Resizes to max_width (preserving aspect ratio) for mobile-optimised delivery.
    PNG stays available during generation so Gemini reference passing works."""
    from PIL import Image as _PILImage

    for png_path in sorted(images_path.glob("scene*.png")):
        jpg_path = png_path.with_suffix(".jpg")
        try:
            img = _PILImage.open(png_path).convert("RGB")
            w, h = img.size
            if w > max_width:
                img = img.resize(
                    (max_width, round(h * max_width / w)),
                    _PILImage.LANCZOS,
                )
            img.save(jpg_path, "JPEG", quality=quality,
                     optimize=True, progressive=True)
            orig_kb = png_path.stat().st_size // 1024
            new_kb  = jpg_path.stat().st_size // 1024
            png_path.unlink()
            logger.info(
                f"Compressed {png_path.name} → {jpg_path.name}: "
                f"{orig_kb} KB → {new_kb} KB ({100 - new_kb * 100 // orig_kb}% smaller)"
            )
        except Exception as e:
            logger.warning(f"JPEG compression failed for {png_path.name}: {e} — keeping PNG")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_images_for_story(story: dict, draft_dir: Path, logs_dir: Path) -> None:
    """
    Generate all scene images. NEVER skips. HALTS pipeline on any failure.
    Does NOT save draft — caller (generate.py) saves only after this returns cleanly.

    Flow:
      1. Discover working Gemini model (or None → full Imagen path).
      2. Scene 1: generate without reference image.
         - If generator == "gemini" → set reference_path for scenes 2-N.
         - If generator == "imagen" → lock all remaining scenes to Imagen (Approach C).
      3. Scenes 2-N: use reference_path for Gemini OR Approach C anchoring for Imagen.
      4. Verify every scene file exists — raise if any missing.
      5. Save image_lineage.json and log lineage summary.

    Pacing: SCENE_SLEEP (70s) enforced between every scene.
    """
    images_path = draft_dir / "images"
    images_path.mkdir(parents=True, exist_ok=True)

    total   = len(story["scenes"])
    results: list[SceneImageResult] = []

    # Discover Gemini model once for the whole session
    gemini_model = _get_working_gemini_model()

    # Tracks scene 1's output path — set only if scene 1 used Gemini successfully
    reference_image_path: Path | None = None

    for i, scene in enumerate(story["scenes"]):
        scene_num   = scene["id"]
        one_based   = i + 1
        label       = f"[IMAGE {one_based}/{total}]"
        target_path = images_path / f"scene{scene_num}.png"

        # ── Determine prompts for this scene ─────────────────────────────────
        if one_based == 1:
            # Scene 1 — no reference, just strong anchors
            prompt_gemini = _build_prompt(scene, story)
            prompt_imagen = _build_prompt(scene, story)
            reference     = None

        else:
            if reference_image_path is not None:
                # Scene 1 was Gemini — use it as visual reference
                prompt_gemini = _build_gemini_reference_prompt(scene, story)
                prompt_imagen = _build_imagen_consistency_prompt(scene, story)  # fallback only
                reference     = reference_image_path
            else:
                # Scene 1 was Imagen (or no Gemini available) — Approach C for all
                prompt_gemini = _build_prompt(scene, story)          # unused (gemini_model=None path)
                prompt_imagen = _build_imagen_consistency_prompt(scene, story)
                reference     = None

        # ── Generate ─────────────────────────────────────────────────────────
        print(f"{label} Generating scene {scene_num}...", end=" ", flush=True)
        t0 = time.time()

        # When scene 1 used Imagen, force Imagen for all remaining scenes
        # (mixing generators across scenes breaks visual consistency)
        effective_gemini = gemini_model if reference_image_path is not None or one_based == 1 else None

        result = _generate_scene_image(
            prompt_gemini = prompt_gemini,
            prompt_imagen = prompt_imagen,
            output_path   = target_path,
            reference_path= reference,
            gemini_model  = effective_gemini,
            scene_label   = label,
            logs_dir      = logs_dir,
        )
        results.append(result)

        elapsed = time.time() - t0
        print(f"✓ ({elapsed:.1f}s, {result.generator})", end="", flush=True)

        # After scene 1: decide reference strategy for the rest of the story
        if one_based == 1:
            if result.generator == "gemini" and result.success and target_path.exists():
                reference_image_path = target_path
                logger.info(f"[IMAGE LINEAGE] Scene 1 used Gemini — reference locked for scenes 2-{total}")
            else:
                reference_image_path = None
                logger.info(
                    f"[IMAGE LINEAGE] Scene 1 used Imagen — "
                    f"switching all remaining scenes to Approach C (Imagen + text anchors)"
                )
                print(
                    f"\n  ℹ  Scene 1 used Imagen. Remaining scenes will use Imagen "
                    f"with locked character anchors (Approach C).",
                    flush=True,
                )

        if one_based < total:
            print(f" — waiting {SCENE_SLEEP}s before next...", flush=True)
            time.sleep(SCENE_SLEEP)
        else:
            print(flush=True)

    # ── Completeness check ────────────────────────────────────────────────────
    missing = [
        s["id"] for s in story["scenes"]
        if not (images_path / f"scene{s['id']}.png").exists()
    ]
    if missing:
        raise RuntimeError(
            f"\n\nIMAGE GENERATION STUCK — scenes {missing} have no image file.\n"
            f"Pipeline halted. Partial draft NOT saved.\n"
            f"Manually resolve, then re-run generate.py."
        )

    # ── Compress PNG → JPEG (done after all scenes so PNGs stay available as references) ──
    _compress_to_jpeg(images_path, total)

    # ── Save image_lineage.json ───────────────────────────────────────────────
    lineage: dict[int, str] = {r.scene_id: r.generator for r in results}
    lineage_path = draft_dir / "image_lineage.json"
    lineage_path.write_text(json.dumps(lineage, indent=2), encoding="utf-8")

    lineage_str = ", ".join(f"{sid}: '{gen}'" for sid, gen in sorted(lineage.items()))
    logger.info(f"[IMAGE LINEAGE] {{{lineage_str}}}")
    print(f"\n[IMAGE LINEAGE] {{{lineage_str}}}", flush=True)

    logger.info(f"All {total}/{total} scene images generated and verified.")
    print(f"✓ All {total} images verified.", flush=True)
