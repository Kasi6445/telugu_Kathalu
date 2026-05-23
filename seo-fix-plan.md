# SEO Fix Plan — Telugu Kathalu
**Date:** 2026-05-23  
**Based on:** `seo-audit-2026-05-23.md`

---

## Fix 1 — Inline story body text into `story/<slug>/index.html`

### Problem
`generate_story_page()` in `lib/seo_writer.py` only replaces the `<head>` block. The body is the unmodified `story.html` slideshow template with empty `<p id="slide-text"></p>`. All scene text loads at runtime via JS. Googlebot must execute JS and await a network fetch before any story text is visible.

### JS Conflict Analysis — confirmed SAFE

**The key question you asked:** does the slideshow JS replace or append to `#slide-text`?

Answer: **it replaces** — `renderWordSpans()` in `story.html` line ~190:
```javascript
function renderWordSpans(text, sceneId) {
  const textEl = document.getElementById('slide-text');
  textEl.innerHTML = '';   // ← clears first, then populates word spans
  textEl.scrollTop = 0;
  // ...appends <span class="word-span"> elements
}
```
`showScene()` also does `textEl.style.opacity = '0'` first, then sets the spans after a 250ms timeout, then fades back in. So the sequence with pre-rendered content is:
1. Page loads → pre-rendered scene 1 text visible in `#slide-text`  
2. JS fetches `stories/index.json` + `stories/<ts>/story.json` (~100–400ms)
3. `showScene(0)` fires → `textEl.opacity = '0'` → 250ms → `innerHTML = ''` → word-spans injected → `opacity = '1'`

**No duplication, no flash.** The pre-rendered text fades out, the interactive version fades in. Identical to how the current blank state animates in.

Similarly `_h1.textContent = story.title` at line ~346 fully replaces the `<h1>` content.

The new `<article id="seo-story-body">` we add is **never referenced by the slideshow JS** — that code only touches `#slide-text`, `#slide-story-title`, `#story-h1`, `#bg-image`, etc. The article stays in the DOM untouched.

### Proposed approach

Add a new function `generate_seo_body(story, slug)` that returns a semantic `<article>` element containing all scene text and the moral. Inject it into the page body via a second regex replace in `generate_story_page()`. The article is rendered below the slideshow in DOM order — visible on the page if users scroll past the full-screen player, so it is **not hidden** and carries no cloaking risk.

Pre-populate `#story-h1` with the actual story title (currently it just says "తెలుగు కథ").

### Proposed diff for `lib/seo_writer.py`

```diff
--- a/lib/seo_writer.py
+++ b/lib/seo_writer.py

+def generate_seo_body(story: dict, slug: str) -> str:
+    """Return a semantic <article> with all scene text for crawler visibility.
+
+    Placed after #moral-screen in the DOM — below the full-screen slideshow,
+    so it is visible content (not hidden) that appears if the user scrolls
+    past the player. JS never touches #seo-story-body, so there is no conflict.
+    """
+    title    = story["title"]
+    moral    = story.get("moral", "")
+    scenes   = story.get("scenes", [])
+    category = story.get("category", "")
+
+    lines = [
+        '<article id="seo-story-body" lang="te">',
+        f'  <h1>{_e(title)}</h1>',
+    ]
+    if category:
+        cat_label = {
+            "neeti": "నీతి కథలు", "podupu": "పొడుపు కథలు",
+            "tenali": "తెనాలి రామ", "panchatantra": "పంచతంత్రం",
+            "ramayana": "రామాయణం", "samethalu": "సామెతలు",
+            "janapada": "జానపదం", "bhagavatam": "భాగవతం",
+        }.get(category, category)
+        lines.append(f'  <p class="seo-category">{_e(cat_label)}</p>')
+    for scene in scenes:
+        text = scene.get("text", "")
+        if text:
+            lines.append(f"  <p>{_e(text)}</p>")
+    if moral:
+        lines += [
+            '  <section class="seo-moral">',
+            f'    <h2>నీతి</h2>',
+            f'    <p>{_e(moral)}</p>',
+            '  </section>',
+        ]
+    lines.append('</article>')
+    return "\n".join(lines)
+
+
 def generate_story_page(story: dict, slug: str, timestamp: str, story_template: str) -> str:
     """Generate full per-story index.html by replacing <head> in the story.html template."""
     new_head = generate_story_head(story, slug, timestamp)
-    return re.sub(r"<head>.*?</head>", new_head, story_template, count=1, flags=re.DOTALL)
+    html = re.sub(r"<head>.*?</head>", new_head, story_template, count=1, flags=re.DOTALL)
+
+    # Pre-populate the hidden h1 with the real story title so crawlers see it
+    # immediately (JS will update it again once story.json loads — no conflict).
+    title_esc = _e(story["title"])
+    html = re.sub(
+        r'(<h1 id="story-h1"[^>]*>)[^<]*(</h1>)',
+        rf'\g<1>{title_esc}\g<2>',
+        html,
+        count=1,
+    )
+
+    # Inject semantic article with all scene text before </body>
+    seo_article = generate_seo_body(story, slug)
+    html = html.replace("</body>", f"\n{seo_article}\n</body>", 1)
+
+    return html
```

### CSS to add to `static/style.css`

```css
/* SEO story body — rendered below the full-screen slideshow.
   Hidden from sight during normal slideshow interaction via the
   fixed/absolute positioning of #slideshow, but visible to crawlers
   and to users without JS (progressive enhancement). */
#seo-story-body {
  padding: 2rem 1.5rem 4rem;
  max-width: 680px;
  margin: 0 auto;
  font-family: 'Noto Sans Telugu', sans-serif;
  line-height: 1.8;
  color: #1a1a2e;
}
#seo-story-body h1 {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
}
#seo-story-body h2 {
  font-size: 1.1rem;
  margin-top: 1.5rem;
}
#seo-story-body p {
  margin: 0.75rem 0;
}
.seo-moral {
  border-left: 3px solid #FF6B35;
  padding-left: 1rem;
  margin-top: 1.5rem;
}
```

> **Note:** After adding this CSS, run `node scripts/bump-css-version.js` per CLAUDE.md rules.

### What this gives Googlebot

- Every `story/<slug>/index.html` raw HTML will contain the full story title, all scene text (concatenated as `<p>` elements), and the moral in a semantic `<article>`.
- Word count in raw HTML will match the story.json content (71–500+ words depending on story).
- The slideshow JS continues to work exactly as today — it hydrates over a non-empty page rather than an empty one.

---

## Fix 2 — Pre-render homepage story links at build time

### Problem
`index.html` contains no `<a href>` links to any story page. All story cards are dynamically created by `renderRecentStories()` and `renderAllStories()` after fetching `stories/index.json`. The static homepage HTML has empty containers and zero crawlable story links. Googlebot discovers stories only via the sitemap.

### JS Conflict Analysis — confirmed SAFE

Both `renderRecentStories()` and `renderAllStories()` do:
```javascript
const container = document.getElementById('recent-stories');  // or all-stories
container.innerHTML = '';   // ← clears static pre-rendered content
stories.forEach(story => {
  const card = document.createElement('a');
  // ... builds full interactive card ...
  container.appendChild(card);
});
```
Static links are cleared and replaced with interactive cards. No visual duplication.

### Proposed new file: `scripts/build_homepage.py`

```python
#!/usr/bin/env python3
"""scripts/build_homepage.py — Pre-render story links into index.html at build time.

Reads stories/index.json and writes static <a href="/story/{slug}/"> links into
the #recent-stories and #all-stories containers in index.html.

The JS renderRecentStories() / renderAllStories() will replace these with the
full interactive cards on page load. The static links exist solely for crawlers.

Usage:
    python scripts/build_homepage.py

Run after every promote.py call (or as part of a post-promote hook).
"""
import html as _html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INDEX_JSON = ROOT / "stories" / "index.json"
HOMEPAGE   = ROOT / "index.html"

RECENT_COUNT = 8   # matches renderRecentStories(allStories.slice(0, 8))

CATEGORIES = {
    "neeti":        "నీతి కథలు",
    "podupu":       "పొడుపు కథలు",
    "tenali":       "తెనాలి రామ",
    "panchatantra": "పంచతంత్రం",
    "ramayana":     "రామాయణం",
    "samethalu":    "సామెతలు",
    "janapada":     "జానపదం",
    "bhagavatam":   "భాగవతం",
}


def _e(val: str) -> str:
    return _html.escape(str(val), quote=True)


def build_recent_html(stories: list) -> str:
    lines = []
    for s in stories[:RECENT_COUNT]:
        slug  = s.get("slug") or s["id"]
        title = _e(s.get("title", slug))
        cat   = CATEGORIES.get(s.get("category", ""), "")
        lines.append(
            f'<a class="h-card" href="/story/{slug}/" aria-label="{title}">'
            f'<div class="h-card-body">'
            f'<div class="h-card-title">{title}</div>'
            f'<div class="h-card-meta">{_e(cat)}</div>'
            f'</div></a>'
        )
    return "\n".join(lines)


def build_all_html(stories: list) -> str:
    lines = []
    for s in stories:
        slug  = s.get("slug") or s["id"]
        title = _e(s.get("title", slug))
        moral = _e(s.get("moral", ""))
        cat   = CATEGORIES.get(s.get("category", ""), "")
        lines.append(
            f'<a class="v-card" href="/story/{slug}/" aria-label="{title}">'
            f'<div class="v-card-body">'
            f'<div class="v-card-title">{title}</div>'
            f'<p class="v-card-moral">💡 {moral}</p>'
            f'<div class="v-card-date">{_e(s.get("date", ""))}</div>'
            f'</div></a>'
        )
    return "\n".join(lines)


def inject(homepage_html: str, container_id: str, inner_html: str) -> str:
    """Replace content between sentinel comments inside a container div."""
    start = f'<!-- STATIC:{container_id}:START -->'
    end   = f'<!-- STATIC:{container_id}:END -->'
    pattern = rf'{re.escape(start)}.*?{re.escape(end)}'
    replacement = f'{start}\n{inner_html}\n{end}'
    new_html, n = re.subn(pattern, replacement, homepage_html, flags=re.DOTALL)
    if n == 0:
        raise ValueError(
            f"Sentinel comments for '{container_id}' not found in index.html.\n"
            f"Add  {start}  and  {end}  inside the container div."
        )
    return new_html


def main():
    with open(INDEX_JSON, encoding="utf-8") as f:
        data = json.load(f)
    stories = data.get("stories", [])

    homepage = HOMEPAGE.read_text(encoding="utf-8")
    homepage = inject(homepage, "recent-stories",  build_recent_html(stories))
    homepage = inject(homepage, "all-stories",     build_all_html(stories))

    HOMEPAGE.write_text(homepage, encoding="utf-8")
    print(f"✅ Pre-rendered {min(len(stories), RECENT_COUNT)} recent + {len(stories)} total story links into index.html")


if __name__ == "__main__":
    main()
```

### Required change to `index.html`

Add sentinel comments inside the two story containers so the script knows where to inject:

```diff
-        <div class="cards-row" id="recent-stories"></div>
+        <div class="cards-row" id="recent-stories"><!-- STATIC:recent-stories:START --><!-- STATIC:recent-stories:END --></div>
```

```diff
-        <div class="stories-grid" id="all-stories"></div>
+        <div class="stories-grid" id="all-stories"><!-- STATIC:all-stories:START --><!-- STATIC:all-stories:END --></div>
```

### Required change to category tiles

Convert the category grid `<button>` tiles from onclick-only to `<a>` with both href and onclick. The onclick returns false after JS handles the filter, so normal link navigation never fires for JS users. Crawlers follow the `href`.

```diff
-          <button class="cat-card cat-bg-neeti" onclick="filterCategory('neeti', null)">
-            <div class="cat-name" data-cat-name="neeti" style="color:#FF9050">నీతి కథలు</div>
-            <div class="cat-count" id="count-neeti">0 కథలు</div>
-          </button>
+          <a class="cat-card cat-bg-neeti" href="/?cat=neeti"
+             onclick="filterCategory('neeti', null); return false;">
+            <div class="cat-name" data-cat-name="neeti" style="color:#FF9050">నీతి కథలు</div>
+            <div class="cat-count" id="count-neeti">0 కథలు</div>
+          </a>
```

Repeat for all 8 category tiles (podupu, tenali, panchatantra, ramayana, samethalu, janapada, bhagavatam).

> **Note:** `/?cat=neeti` is a valid crawlable URL. Googlebot will GET it, receive the same JS shell homepage, and need to execute JS to see filtered content. This does NOT create indexable category pages — it only makes the tiles crawlable. Dedicated static category pages would require a separate build step and are out of scope here.

### Hook into the build pipeline

Add a call to `build_homepage.py` at the end of `promote.py` so homepage links are updated on every story promotion:

```diff
 # In promote.py main(), after seo_writer calls:
     (BASE_DIR / "_redirects").write_text(generate_redirects(_idx["stories"]), encoding="utf-8")
     (BASE_DIR / "sitemap.xml").write_text(generate_sitemap_xml(_idx["stories"]), encoding="utf-8")
     logger.info(f"SEO pages regenerated (slug: {_slug})")
+
+    # Pre-render static story links into index.html for crawler discovery
+    import subprocess
+    subprocess.run(
+        [sys.executable, str(BASE_DIR / "scripts" / "build_homepage.py")],
+        check=True,
+    )
+    logger.info("Homepage static links updated")
```

---

## Fix 3 — CSS version consistency in `seo_writer.py`

### Problem
`lib/seo_writer.py:148` hardcodes `/static/style.css?v=7`. The current CSS version is `v=28`. This means every newly promoted story page gets a stale CSS cache-bust version. Currently 32 of 62 story pages serve `?v=7`.

### Root cause
The CSS version is maintained in three places:
1. `index.html` line 34: `?v=28` ✅
2. `story.html` line 38: `?v=28` ✅  
3. `lib/seo_writer.py` line 148: `?v=7` ❌

`CLAUDE.md` documents the bump process (`node scripts/bump-css-version.js`) but that script only updates `.html` files — it does NOT update `seo_writer.py`.

### Proposed diff for `lib/seo_writer.py`

```diff
--- a/lib/seo_writer.py
+++ b/lib/seo_writer.py

+# Keep in sync with static/style.css cache-bust version in index.html / story.html.
+# When you run scripts/bump-css-version.js, also update this constant.
+CSS_VERSION = 28
+
 ...
 
-        '<link rel="stylesheet" href="/static/style.css?v=7">',
+        f'<link rel="stylesheet" href="/static/style.css?v={CSS_VERSION}">',
```

### Proposed change to `scripts/bump-css-version.js`

The bump script should also update `lib/seo_writer.py`. Add at the end of `bump-css-version.js`:

```javascript
// Also update CSS_VERSION constant in lib/seo_writer.py
const seoWriterPath = path.join(__dirname, '..', 'lib', 'seo_writer.py');
let seoWriter = fs.readFileSync(seoWriterPath, 'utf8');
seoWriter = seoWriter.replace(
  /^CSS_VERSION\s*=\s*\d+/m,
  `CSS_VERSION = ${nextVersion}`
);
fs.writeFileSync(seoWriterPath, seoWriter, 'utf8');
console.log(`Updated CSS_VERSION in lib/seo_writer.py to ${nextVersion}`);
```

### Also update CLAUDE.md

```diff
 ## CSS Version Bump (MANDATORY)
 
 `static/style.css` is cache-busted with a `?v=N` query string across all HTML files.
 
-**Every time `static/style.css` is modified, you MUST bump the version before finishing.**
+**Every time `static/style.css` is modified, you MUST bump the version before finishing.**
+
+The bump script also updates `CSS_VERSION` in `lib/seo_writer.py` — this is critical
+because story pages generated by `promote.py` use `seo_writer.py` for their CSS link.
```

---

## Implementation Checklist

In the order suggested in the audit:

```
[ ] 1. Apply Fix 3 first (CSS version) — 1 line change, lowest risk
        - Edit lib/seo_writer.py: add CSS_VERSION = 28 constant
        - Edit scripts/bump-css-version.js: add seo_writer.py update
        - Edit CLAUDE.md: note seo_writer.py in the bump section

[ ] 2. Apply Fix 1 (body text inlining)
        - Add generate_seo_body() function to lib/seo_writer.py
        - Update generate_story_page() to inject it
        - Pre-populate #story-h1 with real title
        - Add CSS to static/style.css for #seo-story-body styling
        - Bump CSS version via: node scripts/bump-css-version.js

[ ] 3. Apply Fix 2 (homepage static links)
        - Add sentinel comments to index.html (#recent-stories, #all-stories)
        - Convert 8 category <button> tiles to <a href="/?cat=..."> in index.html
        - Write scripts/build_homepage.py
        - Hook build_homepage.py into promote.py

[ ] 4. Rebuild all 62 story pages
        python scripts/backfill_seo.py

[ ] 5. Run homepage build
        python scripts/build_homepage.py

[ ] 6. Deploy to Cloudflare Pages
        git add -p && git commit && git push

[ ] 7. Verify live pages
        curl -s https://www.telugukathalu.in/story/adbhuta-samjiivani-katha/ | grep "seo-story-body"
        # Should return the <article> element with story text

[ ] 8. Request re-indexing in Google Search Console
        Submit 5–10 representative story URLs for inspection

[ ] 9. Wait 2–3 weeks and check Search Console Coverage report
        Look for: thin content warnings, indexed pages count, Core Web Vitals
```

---

## Why Not Use `<noscript>` Instead?

An alternative is wrapping all story text in `<noscript>`:
```html
<noscript><article>...story text...</article></noscript>
```
Google parses `<noscript>` but generally treats it lower-priority than regular DOM content, and its indexing behavior is less predictable. More importantly, it does nothing for Googlebot's rendering pipeline — Googlebot renders JS and would see an empty `<noscript>` block (since Chromium enables JS). The article-in-body approach is unambiguous: the text is always in the DOM, always indexable.

---

## Expected Impact Timeline

| Milestone | Timeframe |
|---|---|
| Pages re-crawled after deploy | 1–7 days |
| Story text appearing in Google's index | 1–3 weeks |
| Coverage report updating | 2–4 weeks |
| Ranking movement visible | 4–8 weeks |
| `dayagala-enugu` (71 words) thin-content warning possible | Monitor at 4 weeks |
