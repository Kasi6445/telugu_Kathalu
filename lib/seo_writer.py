"""lib/seo_writer.py — Static per-story HTML generator for telugukathalu.in.

Public API
----------
generate_story_head(story, slug, timestamp) -> str
generate_story_page(story, slug, timestamp, story_template) -> str
write_story_page(slug, html, output_root=".") -> Path
generate_homepage_jsonld() -> str
generate_redirects(stories_index) -> str
generate_sitemap_xml(stories_index, base_url=BASE_URL) -> str

No GCP calls. No network I/O. Pure stdlib.
"""

import html as _html
import json
import re
from datetime import date as _date
from pathlib import Path

BASE_URL     = "https://www.telugukathalu.in"
_SITE_NAME   = "తెలుగు కథలు"
_TWITTER     = "@telugukathalu"
_ICON_512    = f"{BASE_URL}/static/icon-512.png"
_GA_ID       = "G-39G2696KDV"
_GSV         = "tYMx4Habst2Z266zGxzjvxtzrq8zAvVMljjU4MBXFfc"
# Bumped by scripts/bump-css-version.js — keep in sync with index.html / story.html.
CSS_VERSION  = 31


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trunc(text: str, max_len: int = 155) -> str:
    """Truncate at word boundary; no trailing ellipsis."""
    if len(text) <= max_len:
        return text
    cut = text.rfind(" ", 0, max_len + 1)
    return text[:cut] if cut > 0 else text[:max_len]


def _date_iso(date_str: str) -> str:
    """'2026-04-21' → '2026-04-21T00:00:00+05:30'"""
    return f"{date_str}T00:00:00+05:30"


def _safe_json(obj) -> str:
    """JSON string safe for embedding in <script> tags (escapes </script> injection)."""
    raw = json.dumps(obj, ensure_ascii=False, indent=2)
    return raw.replace("</", "<\\/")


def _e(val: str) -> str:
    """HTML-escape a value for use inside an attribute (quote=True)."""
    return _html.escape(str(val), quote=True)


# ── Core generators ───────────────────────────────────────────────────────────

def generate_story_head(story: dict, slug: str, timestamp: str) -> str:
    """Render the per-story <head>...</head> block as a string."""
    title    = story["title"]
    moral    = story.get("moral", "")
    category = story.get("category", "")
    date_str = story.get("date", "")

    desc      = _trunc(moral)
    date_iso  = _date_iso(date_str) if date_str else ""
    story_url = f"{BASE_URL}/story/{slug}/"
    image_url = f"{BASE_URL}/stories/{timestamp}/images/scene1.jpg"

    jsonld_obj = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": desc,
        "image": [image_url],
        "datePublished": date_iso,
        "dateModified": date_iso,
        "author": {
            "@type": "Organization",
            "name": _SITE_NAME,
            "url": f"{BASE_URL}/",
        },
        "publisher": {
            "@type": "Organization",
            "name": _SITE_NAME,
            "url": f"{BASE_URL}/",
            "logo": {
                "@type": "ImageObject",
                "url": _ICON_512,
            },
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": story_url,
        },
        "inLanguage": "te",
        "articleSection": category,
    }

    lines = [
        "<head>",
        '<base href="/">',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">',
        f'<meta name="google-site-verification" content="{_GSV}" />',
        "",
        "<!-- Per-story SEO -->",
        f"<title>{_e(title)} - {_SITE_NAME}</title>",
        f'<meta name="description" content="{_e(desc)}">',
        f'<link rel="canonical" href="{story_url}">',
        f'<meta name="author" content="{_SITE_NAME}">',
        "",
        "<!-- Open Graph -->",
        '<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{_e(title)}">',
        f'<meta property="og:description" content="{_e(desc)}">',
        f'<meta property="og:url" content="{story_url}">',
        f'<meta property="og:image" content="{image_url}">',
        f'<meta property="og:site_name" content="{_SITE_NAME}">',
        '<meta property="og:locale" content="te_IN">',
        "",
        "<!-- Twitter Card -->",
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:site" content="{_TWITTER}">',
        f'<meta name="twitter:title" content="{_e(title)}">',
        f'<meta name="twitter:description" content="{_e(desc)}">',
        f'<meta name="twitter:image" content="{image_url}">',
        "",
        "<!-- Article JSON-LD -->",
        '<script type="application/ld+json">',
        _safe_json(jsonld_obj),
        "</script>",
        "",
        "<!-- Slug bridge: tells story.html JS which slug/timestamp to load -->",
        "<script>",
        f'  window.STORY_SLUG = "{slug}";',
        f'  window.STORY_TIMESTAMP = "{timestamp}";',
        "</script>",
        "",
        "<!-- Site assets -->",
        '<link rel="icon" href="/favicon.ico">',
        '<link rel="manifest" href="/manifest.json">',
        '<link rel="apple-touch-icon" href="/static/icon-192.png">',
        '<meta name="theme-color" content="#FF6B35">',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="preconnect" href="https://www.googletagmanager.com">',
        f'<link rel="stylesheet" href="/static/style.css?v={CSS_VERSION}">',
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;700&display=swap" rel="stylesheet">',
        "",
        "<!-- Google Analytics -->",
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={_GA_ID}"></script>',
        "<script>",
        "  window.dataLayer = window.dataLayer || [];",
        "  function gtag() { dataLayer.push(arguments); }",
        "  gtag('js', new Date());",
        f"  gtag('config', '{_GA_ID}');",
        "</script>",
        "</head>",
    ]
    return "\n".join(lines)


_CATEGORY_LABELS = {
    "neeti":        "నీతి కథలు",
    "podupu":       "పొడుపు కథలు",
    "tenali":       "తెనాలి రామ",
    "panchatantra": "పంచతంత్రం",
    "ramayana":     "రామాయణం",
    "samethalu":    "సామెతలు",
    "janapada":     "జానపదం",
    "bhagavatam":   "భాగవతం",
}


def generate_seo_body(story: dict) -> str:
    """Return a semantic <article> with all scene text for crawler visibility.

    Injected before </body> in the built story page. The slideshow JS never
    touches #seo-story-body — it only operates on #slide-text, #bg-image, etc.
    — so there is no hydration conflict. The article sits below the full-screen
    player in DOM order: invisible during normal use, visible to crawlers and to
    users without JS.
    """
    title    = story.get("title", "")
    moral    = story.get("moral", "")
    scenes   = story.get("scenes", [])
    category = story.get("category", "")

    lines = ['<article id="seo-story-body" lang="te">']

    if category:
        cat_label = _CATEGORY_LABELS.get(category, category)
        lines.append(f'<p class="seo-category">{_e(cat_label)}</p>')

    lines.append(f'<h1>{_e(title)}</h1>')

    for scene in scenes:
        text = scene.get("text", "").strip()
        if text:
            lines.append(f"<p>{_e(text)}</p>")

    if moral:
        lines += [
            '<section class="seo-moral">',
            '<h2>నీతి</h2>',
            f'<p>{_e(moral)}</p>',
            '</section>',
        ]

    lines.append('</article>')
    return "\n".join(lines)


def generate_story_page(story: dict, slug: str, timestamp: str, story_template: str) -> str:
    """Generate full per-story index.html by replacing <head> in the story.html template."""
    new_head = generate_story_head(story, slug, timestamp)
    html = re.sub(r"<head>.*?</head>", new_head, story_template, count=1, flags=re.DOTALL)

    # Inject semantic article with all scene text before </body>.
    # The article's <h1> is the page's sole h1 — the old hidden #story-h1
    # was removed from story.html. JS never references #seo-story-body.
    seo_article = generate_seo_body(story)
    html = html.replace("</body>", f"\n{seo_article}\n</body>", 1)

    return html


def write_story_page(slug: str, html: str, output_root: str = ".") -> Path:
    """Write to /story/{slug}/index.html, creating the directory if needed."""
    out_dir = Path(output_root) / "story" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")
    return out_file


def generate_homepage_jsonld() -> str:
    """Return WebSite + Organization JSON-LD as a <script> block for index.html."""
    schema = [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "url": f"{BASE_URL}/",
            "name": _SITE_NAME,
            "alternateName": "Telugu Kathalu",
            "description": (
                "తెలుగు కథలు - నీతి కథలు, పంచతంత్రం, తెనాలి రామ, "
                "రామాయణం మరియు మరిన్ని తెలుగు కథలు చదవండి."
            ),
            "inLanguage": "te",
        },
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "url": f"{BASE_URL}/",
            "name": _SITE_NAME,
            "logo": {
                "@type": "ImageObject",
                "url": _ICON_512,
                "width": 512,
                "height": 512,
            },
        },
    ]
    return f'<script type="application/ld+json">\n{_safe_json(schema)}\n</script>'


def generate_redirects(stories_index: list) -> str:
    """Return Cloudflare _redirects file contents.

    Query-string redirects (?id=slug → /story/{slug}/) are handled by
    functions/story.html.js (Cloudflare Pages Function). This only emits
    the bare /story.html catch-all.
    """
    lines = [
        "# Cloudflare _redirects — query-string redirects are handled by",
        "# functions/story.html.js (Pages Function) which issues correct 301s.",
        "# This file only handles the bare /story.html catch-all.",
        "",
        "# Catch-all: bare story.html (no id) → home",
        "/story.html  /  301",
        "",
    ]
    return "\n".join(lines)


def generate_sitemap_xml(stories_index: list, base_url: str = BASE_URL) -> str:
    """Return sitemap.xml with /story/{slug}/ URLs."""
    today = _date.today().isoformat()

    urls = [
        f"  <url>\n"
        f"    <loc>{base_url}/</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>daily</changefreq>\n"
        f"    <priority>1.0</priority>\n"
        f"  </url>"
    ]

    for story in stories_index:
        slug      = story.get("slug") or story["id"]
        lastmod   = story.get("date", today)
        story_url = f"{base_url}/story/{slug}/"
        urls.append(
            f"  <url>\n"
            f"    <loc>{story_url}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>monthly</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
