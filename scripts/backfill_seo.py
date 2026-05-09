"""scripts/backfill_seo.py — Backfill per-story static HTML for every entry in index.json.

Run from repo root:
    python scripts/backfill_seo.py

Generates:
  story/{slug}/index.html  — for each story (Phases 5 + 9)
  _redirects               — Cloudflare 301 rules (Phase 6)
  sitemap.xml              — slug-based URLs + image:image entries (Phase 7)
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from lib.seo_writer import (
    generate_story_page,
    write_story_page,
    generate_redirects,
    generate_sitemap_xml,
)

INDEX_FILE = ROOT / "stories" / "index.json"
STORY_TEMPLATE = (ROOT / "story.html").read_text(encoding="utf-8")


def main():
    with open(INDEX_FILE, encoding="utf-8") as f:
        data = json.load(f)
    stories = data["stories"]
    print(f"Processing {len(stories)} stories from index.json\n")

    # ── Per-story static pages ─────────────────────────────────────────────────
    for entry in stories:
        slug      = entry.get("slug") or entry["id"]
        timestamp = entry["id"]
        story = {
            "title":    entry["title"],
            "moral":    entry.get("moral", ""),
            "category": entry.get("category", ""),
            "date":     entry.get("date", ""),
        }
        html = generate_story_page(story, slug, timestamp, STORY_TEMPLATE)
        out  = write_story_page(slug, html, output_root=str(ROOT))
        print(f"  [ok] {out.relative_to(ROOT)}")

    # ── _redirects ────────────────────────────────────────────────────────────
    redirects_path = ROOT / "_redirects"
    redirects_path.write_text(generate_redirects(stories), encoding="utf-8")
    print(f"\n[ok] _redirects  ({len(stories)} story rules + 1 catch-all)")

    # ── sitemap.xml ───────────────────────────────────────────────────────────
    sitemap_path = ROOT / "sitemap.xml"
    sitemap_path.write_text(generate_sitemap_xml(stories), encoding="utf-8")
    print(f"[ok] sitemap.xml ({len(stories) + 1} URLs with image:image entries)")

    print("\nBackfill complete.")


if __name__ == "__main__":
    main()
