"""
Backfill R2 URLs in story.json thumbnail fields.

For stories with relative thumbnail paths, rewrite them to absolute R2 URLs.

Usage:
  python scripts/backfill_r2_urls.py --check      # Count stories needing fixes
  python scripts/backfill_r2_urls.py --fix        # Apply fixes
"""

import argparse
import json
import sys
from pathlib import Path


R2_BASE_URL = "https://pub-558b12062e854257a35815cd84959ad0.r2.dev"


def needs_backfill(thumbnail: str) -> bool:
    """Check if thumbnail is a relative path (not an absolute URL)."""
    return thumbnail and not thumbnail.startswith("http")


def convert_thumbnail(story_id: str, old_thumbnail: str) -> str:
    """Convert relative path to R2 URL."""
    return f"{R2_BASE_URL}/stories/{story_id}/images/scene1.jpg"


def main():
    parser = argparse.ArgumentParser(description="Backfill R2 URLs in story thumbnails")
    parser.add_argument("--check", action="store_true", help="Count stories needing fixes (dry-run)")
    parser.add_argument("--fix", action="store_true", help="Apply fixes")
    args = parser.parse_args()

    if not args.check and not args.fix:
        parser.print_help()
        sys.exit(1)

    base_dir = Path(__file__).parent.parent
    stories_dir = base_dir / "stories"

    if not stories_dir.exists():
        print(f"ERROR: {stories_dir} not found")
        sys.exit(1)

    # Find all story.json files
    story_files = sorted(stories_dir.glob("*/story.json"))
    print(f"Found {len(story_files)} stories total\n")

    needing_fix = []
    already_fixed = []

    for story_file in story_files:
        story_id = story_file.parent.name
        try:
            with open(story_file, encoding="utf-8") as f:
                story = json.load(f)
        except Exception as e:
            print(f"WARN: Could not read {story_file}: {e}")
            continue

        thumbnail = story.get("thumbnail", "")

        if needs_backfill(thumbnail):
            needing_fix.append((story_id, thumbnail))
        elif thumbnail.startswith("http"):
            already_fixed.append((story_id, thumbnail))

    print(f"Already fixed (R2 URL):     {len(already_fixed)}")
    print(f"Needs backfill (relative):  {len(needing_fix)}")
    print()

    if needing_fix:
        print("Stories needing backfill:")
        for sid, thumb in needing_fix[:10]:  # show first 10
            print(f"  {sid}: {thumb}")
        if len(needing_fix) > 10:
            print(f"  ... and {len(needing_fix) - 10} more")
        print()

    if args.check:
        print(f"[DRY-RUN] Would fix {len(needing_fix)} stories")
        sys.exit(0)

    if args.fix:
        if not needing_fix:
            print("Nothing to fix!")
            sys.exit(0)

        print(f"Fixing {len(needing_fix)} stories...")
        fixed_count = 0

        for story_id, old_thumbnail in needing_fix:
            story_file = stories_dir / story_id / "story.json"
            try:
                with open(story_file, encoding="utf-8") as f:
                    story = json.load(f)

                new_thumbnail = convert_thumbnail(story_id, old_thumbnail)
                story["thumbnail"] = new_thumbnail

                with open(story_file, "w", encoding="utf-8") as f:
                    json.dump(story, f, ensure_ascii=False, indent=2)

                fixed_count += 1
                print(f"  OK {story_id}")
            except Exception as e:
                print(f"  FAIL {story_id}: {e}")

        print(f"\nFixed {fixed_count}/{len(needing_fix)} stories")
        sys.exit(0)


if __name__ == "__main__":
    main()
