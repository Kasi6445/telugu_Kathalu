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

BASE_DIR     = Path(__file__).parent
DRAFTS_DIR   = BASE_DIR / "drafts"
LOGS_DIR     = BASE_DIR / "logs"
R2_BASE_URL  = os.environ.get("R2_BASE_URL", "https://pub-558b12062e854257a35815cd84959ad0.r2.dev")

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
    # Media is served from R2; local dirs are absent after generate-stories.yml
    # deletes them pre-commit. Only run the local file count check when dirs
    # actually exist (local dev workflow).
    n_scenes  = len(story.get("scenes", []))
    audio_dir = draft_dir / "audio"
    image_dir = draft_dir / "images"

    if audio_dir.exists():
        audio_files = sorted(audio_dir.glob("scene*.mp3"))
        if len(audio_files) != n_scenes:
            logger.error(f"Audio incomplete: {len(audio_files)}/{n_scenes} files. Aborting.")
            sys.exit(1)

    if image_dir.exists():
        image_files = sorted(image_dir.glob("scene*.jpg")) + sorted(image_dir.glob("scene*.png"))
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

    # Thumbnail — absolute R2 URL so story.html and OG tags resolve correctly
    # after media is removed from the repo (served from Cloudflare R2).
    story["thumbnail"] = f"{R2_BASE_URL}/stories/{ts}/images/scene1.jpg"
    dest_story_file = dest_dir / "story.json"
    with open(dest_story_file, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    # ── Update index.json ─────────────────────────────────────────────────────
    from lib.index_writer import update_index, update_sitemap
    update_index(story)
    update_sitemap()

    # ── Generate per-story static HTML + refresh _redirects + sitemap.xml ────
    from lib.seo_writer import (
        generate_story_page, write_story_page,
        generate_redirects, generate_sitemap_xml,
    )
    with open(BASE_DIR / "stories" / "index.json", encoding="utf-8") as _f:
        _idx = json.load(_f)
    _entry = next(s for s in _idx["stories"] if s["id"] == story["id"])
    _slug = _entry["slug"]
    _template = (BASE_DIR / "story.html").read_text(encoding="utf-8")
    _html = generate_story_page(story, _slug, story["id"], _template)
    write_story_page(_slug, _html, output_root=str(BASE_DIR))
    (BASE_DIR / "_redirects").write_text(generate_redirects(_idx["stories"]), encoding="utf-8")
    (BASE_DIR / "sitemap.xml").write_text(generate_sitemap_xml(_idx["stories"]), encoding="utf-8")
    logger.info(f"SEO pages regenerated (slug: {_slug})")

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
