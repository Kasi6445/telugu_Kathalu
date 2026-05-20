#!/usr/bin/env python3
"""
scripts/regen_audio.py — Regenerate audio for one or all scenes in a draft.

Usage:
  python scripts/regen_audio.py <draft_id>              # all scenes
  python scripts/regen_audio.py <draft_id> --scene 3    # one scene only

Examples:
  python scripts/regen_audio.py 20260519_152539
  python scripts/regen_audio.py 20260519_152539 --scene 3

The existing MP3 files are deleted first so the TTS cache doesn't skip them.
story.json and images are untouched.
"""
import json
import logging
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

DRAFTS_DIR = BASE_DIR / "drafts"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("regen_audio")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Regenerate TTS audio for a draft")
    parser.add_argument("draft_id", help="Draft timestamp, e.g. 20260519_152539")
    parser.add_argument("--scene", type=int, metavar="N",
                        help="Regenerate only this scene number (default: all scenes)")
    args = parser.parse_args()

    draft_dir  = DRAFTS_DIR / args.draft_id
    story_file = draft_dir / "story.json"
    audio_dir  = draft_dir / "audio"

    if not story_file.exists():
        logger.error(f"story.json not found: {story_file}")
        sys.exit(1)

    with open(story_file, "r", encoding="utf-8") as f:
        story = json.load(f)

    scenes     = story["scenes"]
    voice_name = story.get("voice", "te-IN-Chirp3-HD-Fenrir")
    total      = len(scenes)

    # Filter to requested scene(s)
    if args.scene is not None:
        scenes = [s for s in scenes if s["id"] == args.scene]
        if not scenes:
            logger.error(f"Scene {args.scene} not found in story")
            sys.exit(1)

    logger.info(f"Draft : {args.draft_id}")
    logger.info(f"Title : {story.get('title', '—')}")
    logger.info(f"Voice : {voice_name}")
    logger.info(f"Scenes: {[s['id'] for s in scenes]}")

    from lib.tts import _synthesize_scene_file

    audio_dir.mkdir(exist_ok=True)

    for scene in scenes:
        out = audio_dir / f"scene{scene['id']}.mp3"

        # Delete existing file so cache doesn't skip it
        if out.exists():
            out.unlink()
            logger.info(f"Deleted existing {out.name}")

        print(f"\n🎙️  Synthesising scene {scene['id']}/{total}...", flush=True)
        ok = _synthesize_scene_file(
            text         = scene["text"],
            voice_name   = voice_name,
            output_path  = out,
            scene_num    = scene["id"],
            total_scenes = total,
            scene_context= scene.get("scene_visual", ""),
        )

        if ok:
            kb = out.stat().st_size // 1024
            print(f"   ✅ scene{scene['id']}.mp3 saved ({kb} KB)", flush=True)
        else:
            print(f"   ❌ scene{scene['id']}.mp3 FAILED", flush=True)

    print(f"\nDone. Preview: python preview_draft.py {args.draft_id}")


if __name__ == "__main__":
    main()
