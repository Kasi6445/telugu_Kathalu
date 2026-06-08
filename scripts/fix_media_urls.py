"""
scripts/fix_media_urls.py

Fix all broken media URLs across:
  1. stories/index.json  — relative thumbnail paths → R2 URLs
  2. story/{slug}/index.html — www.telugukathalu.in domain → R2 CDN domain

Run from project root:
    python scripts/fix_media_urls.py --check   # dry-run, show counts
    python scripts/fix_media_urls.py --fix     # apply changes
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT     = Path(__file__).parent.parent
R2_BASE  = "https://pub-558b12062e854257a35815cd84959ad0.r2.dev"
OLD_DOMAIN = "https://www.telugukathalu.in"


# ── Fix 1: stories/index.json thumbnails ──────────────────────────────────────

def fix_index_json(dry_run: bool) -> int:
    index_path = ROOT / "stories" / "index.json"
    with open(index_path, encoding="utf-8") as f:
        idx = json.load(f)

    fixed = 0
    for entry in idx["stories"]:
        thumb = entry.get("thumbnail", "")
        if thumb and not thumb.startswith("https://"):
            # relative path like "stories/{id}/images/scene1.jpg"
            clean = thumb.lstrip("/")
            entry["thumbnail"] = f"{R2_BASE}/{clean}"
            fixed += 1

    if fixed and not dry_run:
        tmp = index_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        tmp.replace(index_path)

    return fixed


# ── Fix 2: story/{slug}/index.html OG/JSON-LD image URLs ─────────────────────

def fix_story_html_files(dry_run: bool) -> tuple[int, int]:
    """Returns (files_fixed, replacements_total)."""
    html_files = sorted((ROOT / "story").glob("*/index.html"))
    files_fixed = 0
    replacements_total = 0

    for p in html_files:
        text = p.read_text(encoding="utf-8")
        # Replace old domain with R2 CDN for all /stories/... media paths
        new_text = text.replace(
            f"{OLD_DOMAIN}/stories/",
            f"{R2_BASE}/stories/",
        )
        count = text.count(f"{OLD_DOMAIN}/stories/")
        if count:
            files_fixed += 1
            replacements_total += count
            if not dry_run:
                p.write_text(new_text, encoding="utf-8")

    return files_fixed, replacements_total


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Dry-run — show counts only")
    parser.add_argument("--fix",   action="store_true", help="Apply fixes")
    args = parser.parse_args()

    if not args.check and not args.fix:
        parser.print_help()
        sys.exit(1)

    dry_run = args.check

    print("Scanning for broken media URLs ...\n")

    # Fix 1
    index_fixed = fix_index_json(dry_run)
    print(f"stories/index.json  — relative thumbnails to fix : {index_fixed}")

    # Fix 2
    html_files_fixed, html_replacements = fix_story_html_files(dry_run)
    print(f"story/*/index.html  — files with old domain URLs : {html_files_fixed}  ({html_replacements} replacements)")

    print()
    total = index_fixed + html_files_fixed
    if dry_run:
        print(f"[DRY-RUN] Would fix {index_fixed} index.json entries + {html_files_fixed} HTML files")
    else:
        print(f"Fixed {index_fixed} index.json entries + {html_files_fixed} HTML files  ({html_replacements} URL replacements)")
        print("\nDone.")


if __name__ == "__main__":
    main()
