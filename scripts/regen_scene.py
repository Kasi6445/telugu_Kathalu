#!/usr/bin/env python3
"""
scripts/regen_scene.py — Regenerate a single scene image in an existing draft.

Usage:
  python scripts/regen_scene.py <draft_id> <scene_number>

Example:
  python scripts/regen_scene.py 20260519_152539 3

What it does:
  1. Loads story.json from drafts/<id>/
  2. Injects the canonical mythology character description for any
     supporting character named in the scene's image_prompt (if applicable)
  3. Uses scene 1 as the protagonist visual reference (for character consistency)
  4. Regenerates only the requested scene image
  5. Saves as scene<N>.jpg  (replaces the old file)

The rest of the draft (story.json, audio, other images) is untouched.
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
DRAFTS_DIR = BASE_DIR / "drafts"
LOGS_DIR   = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("regen_scene")


def _inject_supporting_character(scene: dict, story: dict,
                                  character_override: str | None = None) -> dict:
    """
    Inject the canonical mythology character description into this scene's image_prompt.

    character_override: when provided, use this exact character name (bypasses auto-detect).
    Auto-detect scans for the character most prominently acting in the scene (subject of
    the main action), not just mentioned. Use --character on the CLI when auto-detect
    picks a referenced-but-absent character (e.g. 'Rama' mentioned in passing while
    Lakshmana is the one physically doing the action).
    """
    category = story.get("category", "")
    mythology_categories = {"ramayana", "bhagavatam"}
    if category not in mythology_categories:
        return scene

    from lib.mythology_knowledge import CHARACTER_ANCHORS, get_character_anchor

    existing_prompt = scene.get("image_prompt", "")

    if character_override:
        # Explicit override: strip existing block and re-inject with specified character
        if "SUPPORTING CHARACTER" in existing_prompt:
            existing_prompt = existing_prompt[:existing_prompt.index(" SUPPORTING CHARACTER")].rstrip()
            scene["image_prompt"] = existing_prompt
        anchor = get_character_anchor(character_override)
        if anchor:
            logger.info(f"Using override character '{character_override}'")
        else:
            anchor = (f"{character_override} — a well-known Hindu mythology figure, "
                      f"depicted accurately per canonical tradition.")
            logger.warning(f"No canonical anchor for '{character_override}' — using fallback description")
        scene["image_prompt"] = existing_prompt + f" SUPPORTING CHARACTER also in this scene: {anchor}"
        return scene

    # No --character override: keep story.json image_prompt exactly as-is.
    # story.json already has correct SUPPORTING CHARACTER blocks (or correctly omits them)
    # from the original generation pipeline. Do not auto-inject.
    logger.info("No --character override — using image_prompt from story.json as-is")

    return scene


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Regenerate a single scene image in a draft")
    parser.add_argument("draft_id",   help="Draft timestamp folder name, e.g. 20260519_152539")
    parser.add_argument("scene_num",  type=int, help="Scene number to regenerate (1-based)")
    parser.add_argument("--character", metavar="NAME",
                        help="Override: canonical name of the supporting character who physically "
                             "appears in this scene (e.g. 'Lakshmana'). Use when auto-detection "
                             "picks the wrong character.")
    args = parser.parse_args()

    draft_id   = args.draft_id
    scene_num  = args.scene_num
    draft_dir  = DRAFTS_DIR / draft_id
    story_file = draft_dir / "story.json"
    images_dir = draft_dir / "images"

    if not story_file.exists():
        logger.error(f"story.json not found: {story_file}")
        sys.exit(1)

    with open(story_file, "r", encoding="utf-8") as f:
        story = json.load(f)

    # Find the scene
    scene = next((s for s in story["scenes"] if s["id"] == scene_num), None)
    if scene is None:
        logger.error(f"Scene {scene_num} not found in story (scenes: {[s['id'] for s in story['scenes']]})")
        sys.exit(1)

    logger.info(f"Draft  : {draft_id}")
    logger.info(f"Scene  : {scene_num}")
    logger.info(f"Title  : {story.get('title', '—')}")

    # Inject supporting character anchor if needed
    scene = _inject_supporting_character(scene, story, character_override=args.character)

    from lib.image_gen import (
        _build_prompt,
        _get_working_gemini_model,
        _call_gemini_generate,
        _call_imagen_generate,
        _RETRY_WAITS,
    )

    full_prompt = _build_prompt(scene, story)

    print(f"\n📝 Image prompt (scene {scene_num}):\n{full_prompt[:600]}...\n")

    # Reference image: use scene 1 jpg for protagonist consistency
    ref_path: Path | None = None
    scene1_jpg = images_dir / "scene1.jpg"
    if scene_num != 1 and scene1_jpg.exists():
        ref_path = scene1_jpg
        logger.info(f"Using scene1.jpg as protagonist reference")

    output_path = images_dir / f"scene{scene_num}.png"  # generate PNG first, then compress

    # Discover Gemini model
    gemini_model = _get_working_gemini_model()

    retry_waits = list(_RETRY_WAITS)
    success = False

    for attempt in range(1, len(_RETRY_WAITS) + 2):
        try:
            if gemini_model:
                from google.genai import types

                from lib.config import make_client
                client = make_client()

                parts = []
                if ref_path and ref_path.exists():
                    # Detect mime type from extension
                    mime = "image/jpeg" if ref_path.suffix.lower() == ".jpg" else "image/png"
                    parts.append(types.Part(inline_data=types.Blob(
                        data=ref_path.read_bytes(), mime_type=mime
                    )))
                    prompt_text = (
                        "Continue the same illustration style from the reference image. "
                        "The protagonist looks identical to the reference — same face, same clothing, same colors. "
                        + full_prompt
                    )
                else:
                    prompt_text = full_prompt

                parts.append(types.Part(text=prompt_text))

                response = client.models.generate_content(
                    model=gemini_model,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    ),
                )

                for part in response.candidates[0].content.parts:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        output_path.write_bytes(part.inline_data.data)
                        logger.info(f"Image saved via Gemini: {output_path.name}")
                        success = True
                        break

                if not success:
                    logger.warning("Gemini returned no image data — falling back to Imagen")
                    gemini_model = None
                    continue

            else:
                success = _call_imagen_generate(full_prompt, output_path)

            if success:
                break

        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if retry_waits:
                    wait = retry_waits.pop(0)
                    logger.warning(f"Rate limited — sleeping {wait}s then retrying")
                    print(f"\n  ⏸  Rate limited. Waiting {wait}s...", flush=True)
                    time.sleep(wait)
                else:
                    logger.error("Rate limit persisted through all retries")
                    sys.exit(1)
            elif gemini_model:
                logger.warning(f"Gemini error — falling back to Imagen: {exc}")
                gemini_model = None
                continue
            else:
                logger.error(f"Image generation failed: {exc}")
                sys.exit(1)

    if not success:
        logger.error("Image generation failed after all retries")
        sys.exit(1)

    # Compress PNG → JPEG and replace old scene3.jpg
    from PIL import Image as _PIL
    jpg_path = images_dir / f"scene{scene_num}.jpg"

    img = _PIL.open(output_path).convert("RGB")
    w, h = img.size
    if w > 1024:
        img = img.resize((1024, round(h * 1024 / w)), _PIL.LANCZOS)
    img.save(jpg_path, "JPEG", quality=82, optimize=True, progressive=True)
    output_path.unlink()  # remove the .png

    size_kb = jpg_path.stat().st_size // 1024
    print(f"\n✅ Scene {scene_num} regenerated: {jpg_path.name} ({size_kb} KB)")
    print(f"   Draft: drafts/{draft_id}/")
    print(f"   Preview: python preview_draft.py {draft_id}")


if __name__ == "__main__":
    main()
