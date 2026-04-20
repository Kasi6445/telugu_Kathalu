import json
import logging
import shutil
from pathlib import Path

from lib.config import INDEX_FILE, STORIES_DIR, BASE_URL

logger = logging.getLogger(__name__)


def update_index(story: dict):
    """Atomically insert story entry at the top of stories/index.json."""
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"stories": []}

    # Remove duplicate entry for same ID (idempotency)
    index["stories"] = [s for s in index["stories"] if s["id"] != story["id"]]

    entry = {
        "id":             story["id"],
        "title":          story["title"],
        "moral":          story["moral"],
        "thumbnail":      story["thumbnail"],
        "date":           story["date"],
        "category":       story["category"],
        "subcategory":    story["subcategory"],
        "topic":          story["topic"],
        "voice":          story.get("voice", ""),
        "schema_version": 2,
    }
    index["stories"].insert(0, entry)

    tmp = INDEX_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    shutil.move(str(tmp), str(INDEX_FILE))
    logger.info(f"index.json updated — {len(index['stories'])} stories total")


def update_sitemap():
    """Regenerate sitemap.xml from all folders under stories/."""
    base = STORIES_DIR.parent
    urls = [
        f"  <url>\n"
        f"    <loc>{BASE_URL}/</loc>\n"
        f"    <changefreq>daily</changefreq>\n"
        f"    <priority>1.0</priority>\n"
        f"  </url>"
    ]

    for folder in sorted(STORIES_DIR.iterdir()):
        if folder.is_dir():
            urls.append(
                f"  <url>\n"
                f"    <loc>{BASE_URL}/story.html?id={folder.name}</loc>\n"
                f"    <changefreq>weekly</changefreq>\n"
                f"    <priority>0.8</priority>\n"
                f"  </url>"
            )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )

    sitemap_path = base / "sitemap.xml"
    sitemap_path.write_text(sitemap, encoding="utf-8")
    logger.info(f"sitemap.xml updated — {len(urls)} URLs")
