import json
import logging
import re
import shutil
from pathlib import Path

from lib.config import INDEX_FILE, STORIES_DIR, BASE_URL

logger = logging.getLogger(__name__)

# ── Telugu → Roman transliteration map ───────────────────────────────────────
# Consonants include inherent 'a'; stripped when followed by virama or matra.
_TEL = {
    # Independent vowels
    'అ': 'a',  'ఆ': 'aa', 'ఇ': 'i',  'ఈ': 'ii',
    'ఉ': 'u',  'ఊ': 'uu', 'ఋ': 'ru',
    'ఎ': 'e',  'ఏ': 'ee', 'ఐ': 'ai',
    'ఒ': 'o',  'ఓ': 'oo', 'ఔ': 'au',
    # Consonants (with inherent 'a')
    'క': 'ka',  'ఖ': 'kha', 'గ': 'ga',  'ఘ': 'gha', 'ఙ': 'nga',
    'చ': 'cha', 'ఛ': 'chha','జ': 'ja',  'ఝ': 'jha', 'ఞ': 'nja',
    'ట': 'ta',  'ఠ': 'tha', 'డ': 'da',  'ఢ': 'dha', 'ణ': 'na',
    'త': 'ta',  'థ': 'tha', 'ద': 'da',  'ధ': 'dha', 'న': 'na',
    'ప': 'pa',  'ఫ': 'pha', 'బ': 'ba',  'భ': 'bha', 'మ': 'ma',
    'య': 'ya',  'ర': 'ra',  'ల': 'la',  'వ': 'va',
    'శ': 'sha', 'ష': 'sha', 'స': 'sa',  'హ': 'ha',
    'ళ': 'la',  'ఱ': 'ra',
    # Vowel matras (replace inherent 'a' of preceding consonant)
    'ా': 'aa', 'ి': 'i',  'ీ': 'ii',
    'ు': 'u',  'ూ': 'uu', 'ృ': 'ru',
    'ె': 'e',  'ే': 'ee', 'ై': 'ai',
    'ొ': 'o',  'ో': 'oo', 'ౌ': 'au',
    # Special marks
    'ం': 'm',  # anusvara
    'ః': 'h',  # visarga
    'ఁ': 'n',  # chandrabindu
    '్': '',   # virama — handled in loop to strip preceding 'a'
    # Telugu digits
    '౦': '0', '౧': '1', '౨': '2', '౧': '1', '౩': '3',
    '౪': '4', '౫': '5', '౬': '6', '౭': '7', '౮': '8', '౯': '9',
}

# Characters that are vowel matras (they replace the consonant's trailing 'a')
_MATRAS = set('ాిీుూృెేైొోౌ')
_VIRAMA = '్'


def make_slug(title: str) -> str:
    """Convert a Telugu story title to a URL-friendly ASCII slug.

    Examples:
      "స్నేహం యొక్క విలువ"       → "sneham-yokka-viluva"
      "దయగల ఏనుగు"               → "dayagala-enugu"
      "ఐక్యతలో బలం"              → "aikyatalo-balam"
    """
    chars = list(title)
    out = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ''

        if ch == _VIRAMA:
            # Already consumed by previous consonant look-ahead — skip
            i += 1
            continue

        mapped = _TEL.get(ch)

        if mapped is not None:
            # Consonant followed by virama: strip inherent 'a'
            if nxt == _VIRAMA and mapped.endswith('a') and len(mapped) > 1:
                out.append(mapped[:-1])
                i += 2  # consume consonant + virama
                continue
            # Consonant followed by vowel matra: strip inherent 'a', matra appends its own
            if nxt in _MATRAS and mapped.endswith('a') and len(mapped) > 1:
                out.append(mapped[:-1])
            else:
                out.append(mapped)
        elif ch.isascii():
            out.append(ch.lower() if ch.isalpha() else ('-' if ch in ' -_' else ''))

        i += 1

    slug = ''.join(out)
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def _ensure_unique_slug(slug: str, existing: list[dict]) -> str:
    """Append a numeric suffix if slug already exists in index."""
    taken = {s.get('slug', '') for s in existing}
    if slug not in taken:
        return slug
    n = 2
    while f"{slug}-{n}" in taken:
        n += 1
    return f"{slug}-{n}"


# ── Index writer ──────────────────────────────────────────────────────────────

def update_index(story: dict):
    """Atomically insert story entry at the top of stories/index.json."""
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"stories": []}

    # Remove duplicate entry for same ID (idempotency)
    index["stories"] = [s for s in index["stories"] if s["id"] != story["id"]]

    slug = make_slug(story["title"])
    slug = _ensure_unique_slug(slug, index["stories"])

    entry = {
        "id":             story["id"],
        "slug":           slug,
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
    logger.info(f"index.json updated — {len(index['stories'])} stories total (slug: {slug})")


# ── Sitemap writer ────────────────────────────────────────────────────────────

def update_sitemap():
    """Regenerate sitemap.xml from stories/index.json using slug-based URLs."""
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"stories": []}

    urls = [
        f"  <url>\n"
        f"    <loc>{BASE_URL}/</loc>\n"
        f"    <changefreq>daily</changefreq>\n"
        f"    <priority>1.0</priority>\n"
        f"  </url>"
    ]

    for story in index["stories"]:
        url_id = story.get("slug") or story["id"]
        urls.append(
            f"  <url>\n"
            f"    <loc>{BASE_URL}/story.html?id={url_id}</loc>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )

    sitemap_path = INDEX_FILE.parent.parent / "sitemap.xml"
    sitemap_path.write_text(sitemap, encoding="utf-8")
    logger.info(f"sitemap.xml updated — {len(urls)} URLs")
