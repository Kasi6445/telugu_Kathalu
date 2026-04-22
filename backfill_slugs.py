"""
backfill_slugs.py — One-time script to add 'slug' field to every story.json.

Reads slugs from stories/index.json (already populated) and writes the slug
into the matching stories/<id>/story.json file.

Safe to re-run (idempotent — skips files that already have the correct slug).

Usage:
  python backfill_slugs.py
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR    = Path(__file__).parent
INDEX_FILE  = BASE_DIR / "stories" / "index.json"
STORIES_DIR = BASE_DIR / "stories"


def main():
    if not INDEX_FILE.exists():
        print("ERROR: stories/index.json not found")
        sys.exit(1)

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    stories = index.get("stories", [])
    updated = 0
    skipped = 0
    missing = 0

    for entry in stories:
        story_id = entry.get("id")
        slug     = entry.get("slug")

        if not story_id or not slug:
            print(f"SKIP  {story_id}: no slug in index.json — run update_index first")
            skipped += 1
            continue

        story_file = STORIES_DIR / story_id / "story.json"
        if not story_file.exists():
            print(f"MISS  {story_id}: story.json not found")
            missing += 1
            continue

        with open(story_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("slug") == slug:
            print(f"OK    {story_id}: slug already '{slug}'")
            skipped += 1
            continue

        data["slug"] = slug

        tmp = story_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(story_file)

        print(f"PATCH {story_id}: slug = '{slug}'")
        updated += 1

    print()
    print(f"Done — {updated} updated, {skipped} skipped, {missing} missing")


if __name__ == "__main__":
    main()
