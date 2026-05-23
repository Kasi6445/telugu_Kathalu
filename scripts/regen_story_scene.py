#!/usr/bin/env python3
"""
scripts/regen_story_scene.py — Regenerate a single scene image in a promoted story.

Usage:
  python scripts/regen_story_scene.py <story_id> <scene_number>

Example:
  python scripts/regen_story_scene.py 20260522_170828 5

What it does:
  1. Loads story.json from stories/<id>/
  2. Regenerates only the requested scene image using the current image_prompt
  3. Saves as scene<N>.jpg (replaces the old file)
  4. Uses scene1.jpg as protagonist visual reference for consistency

The rest of the story (story.json, audio, other images) is untouched.
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR    = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
STORIES_DIR = BASE_DIR / "stories"
LOGS_DIR    = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("regen_story_scene")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Regenerate a single scene image in a promoted story")
    parser.add_argument("story_id",  help="Story timestamp folder name, e.g. 20260522_170828")
    parser.add_argument("scene_num", type=int, help="Scene number to regenerate (1-based)")
    args = parser.parse_args()

    story_id   = args.story_id
    scene_num  = args.scene_num
    story_dir  = STORIES_DIR / story_id
    story_file = story_dir / "story.json"
    images_dir = story_dir / "images"

    if not story_file.exists():
        logger.error(f"story.json not found: {story_file}")
        sys.exit(1)

    with open(story_file, "r", encoding="utf-8") as f:
        story = json.load(f)

    scene = next((s for s in story["scenes"] if s["id"] == scene_num), None)
    if scene is None:
        logger.error(f"Scene {scene_num} not found in story")
        sys.exit(1)

    logger.info(f"Story  : {story_id}")
    logger.info(f"Scene  : {scene_num}")
    logger.info(f"Title  : {story.get('title', '—')}")

    from lib.config import STYLE_LOCK
    from lib.image_gen import (
        _DIRECTOR_PREFIX,
        _get_working_gemini_model,
        _call_imagen_generate,
        _RETRY_WAITS,
    )

    full_prompt = (
        f"{_DIRECTOR_PREFIX}"
        f"{story['main_character']} "
        f"{story['setting']} "
        f"{scene.get('image_prompt', '')} "
        f"{STYLE_LOCK}"
    )

    print(f"\nImage prompt (scene {scene_num}):\n{full_prompt[:600]}...\n")

    ref_path = None
    scene1_jpg = images_dir / "scene1.jpg"
    if scene_num != 1 and scene1_jpg.exists():
        ref_path = scene1_jpg
        logger.info("Using scene1.jpg as protagonist reference")

    output_path = images_dir / f"scene{scene_num}.png"

    gemini_model = _get_working_gemini_model()
    retry_waits  = list(_RETRY_WAITS)
    success      = False

    for attempt in range(1, len(_RETRY_WAITS) + 2):
        try:
            if gemini_model:
                from google.genai import types
                from lib.config import make_client
                client = make_client()

                parts = []
                if ref_path and ref_path.exists():
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

    from PIL import Image as _PIL
    jpg_path = images_dir / f"scene{scene_num}.jpg"

    img = _PIL.open(output_path).convert("RGB")
    w, h = img.size
    if w > 1024:
        img = img.resize((1024, round(h * 1024 / w)), _PIL.LANCZOS)
    img.save(jpg_path, "JPEG", quality=82, optimize=True, progressive=True)
    output_path.unlink()

    size_kb = jpg_path.stat().st_size // 1024
    print(f"\nScene {scene_num} regenerated: {jpg_path.name} ({size_kb} KB)")
    print(f"Story: stories/{story_id}/")


if __name__ == "__main__":
    main()
