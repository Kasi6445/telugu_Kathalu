#!/usr/bin/env python3
"""
promote.py — Move an approved draft into stories/ and update index + sitemap.

Usage:
  python promote.py <timestamp>
  python promote.py 20260420_153012
"""
import json
import logging
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"
LOGS_DIR   = BASE_DIR / "logs"

LOGS_DIR.mkdir(exist_ok=True)

_log_file = LOGS_DIR / f"promote_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("promote")


def main():
    if len(sys.argv) != 2:
        print("Usage: python promote.py <timestamp>")
        sys.exit(1)

    ts        = sys.argv[1]
    draft_dir = DRAFTS_DIR / ts
    story_file = draft_dir / "story.json"

    if not draft_dir.exists():
        logger.error(f"Draft '{ts}' not found in drafts/")
        sys.exit(1)

    if not story_file.exists():
        logger.error(f"story.json missing in drafts/{ts}/")
        sys.exit(1)

    with open(story_file, "r", encoding="utf-8") as f:
        story = json.load(f)

    # ── Completeness check ────────────────────────────────────────────────────
    audio_files = sorted((draft_dir / "audio").glob("scene*.mp3")) if (draft_dir / "audio").exists() else []
    image_dir   = draft_dir / "images"
    image_files = sorted(image_dir.glob("scene*.jpg")) + sorted(image_dir.glob("scene*.png")) if image_dir.exists() else []
    n_scenes    = len(story.get("scenes", []))

    if len(audio_files) != n_scenes:
        logger.error(f"Audio incomplete: {len(audio_files)}/{n_scenes} files. Aborting.")
        sys.exit(1)

    if len(image_files) != n_scenes:
        logger.error(f"Images incomplete: {len(image_files)}/{n_scenes} files. Aborting.")
        sys.exit(1)

    # ── Move draft → stories/<timestamp>/ ────────────────────────────────────
    from lib.config import STORIES_DIR
    dest_dir = STORIES_DIR / ts

    if dest_dir.exists():
        logger.warning(f"stories/{ts}/ already exists — overwriting")
        shutil.rmtree(dest_dir)

    shutil.copytree(str(draft_dir), str(dest_dir))
    logger.info(f"Copied drafts/{ts}/ → stories/{ts}/")

    # Update thumbnail path to reflect new location
    story["thumbnail"] = f"stories/{ts}/images/scene1.jpg"
    dest_story_file = dest_dir / "story.json"
    with open(dest_story_file, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    # ── Update index.json ─────────────────────────────────────────────────────
    from lib.index_writer import update_index, update_sitemap
    update_index(story)
    update_sitemap()

    # ── Remove draft ──────────────────────────────────────────────────────────
    def _force_remove(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(draft_dir, onexc=_force_remove)
    logger.info(f"Removed drafts/{ts}/")

    print(f"\n🎉 Promoted : stories/{ts}/")
    print(f"📖 Title    : {story.get('title', '—')}")
    print(f"📂 Category : {story.get('category', '—')} / {story.get('subcategory', '—')}")
    print()


if __name__ == "__main__":
    main()
