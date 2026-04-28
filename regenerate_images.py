#!/usr/bin/env python3
"""
Regenerate images for an existing draft without touching audio or story text.

Usage:
  python regenerate_images.py 20260427_220859
"""
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from lib.config import DRAFTS_DIR, LOGS_DIR
from lib.image_gen import generate_images_for_story

LOGS_DIR.mkdir(exist_ok=True)

_log_file = LOGS_DIR / f"regen_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("regenerate_images")


def main():
    if len(sys.argv) != 2:
        print("Usage: python regenerate_images.py <draft_timestamp>")
        print("  e.g: python regenerate_images.py 20260427_220859")
        sys.exit(1)

    timestamp = sys.argv[1]
    draft_dir = DRAFTS_DIR / timestamp

    if not draft_dir.exists():
        print(f"Draft not found: {draft_dir}")
        sys.exit(1)

    story_path = draft_dir / "story.json"
    if not story_path.exists():
        print(f"No story.json in {draft_dir}")
        sys.exit(1)

    story = json.loads(story_path.read_text(encoding="utf-8"))

    print(f"\n📖 Story  : {story['title']}")
    print(f"📂 Draft  : drafts/{timestamp}/")
    print(f"🖼️  Scenes : {len(story['scenes'])}")

    # Wipe existing images so generation starts clean
    images_dir = draft_dir / "images"
    images_dir.mkdir(exist_ok=True)
    removed = 0
    for f in images_dir.glob("scene*.*"):
        f.unlink()
        removed += 1
    if removed:
        print(f"🗑️  Removed {removed} existing image(s)")

    print("\nGenerating images...\n")
    generate_images_for_story(story, draft_dir, LOGS_DIR)

    # Update thumbnail extension in story.json to match new files
    new_images = list(images_dir.glob("scene*.*"))
    if new_images:
        new_ext = new_images[0].suffix.lstrip(".")
        story["thumbnail"] = f"stories/{timestamp}/images/scene1.{new_ext}"
        story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ story.json thumbnail updated → scene1.{new_ext}")

    print(f"\n🎉 Done. Images saved to drafts/{timestamp}/images/")
    print(f"   Preview : python preview_draft.py {timestamp}")
    print(f"   Promote : python promote.py {timestamp}")


if __name__ == "__main__":
    main()
