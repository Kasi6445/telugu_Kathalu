# Telugu Katalu — Test Plan

Manual verification checklist for every feature. Run after any significant change before pushing to production.

---

## 1. Generation pipeline

### Dry run
```bash
python generate.py --dry-run
```
- [ ] Prints category, subcategory, topic, no API calls made
- [ ] Category is NOT always `neeti` (balancer working)
- [ ] Topic is not a duplicate of an already-published story

### Full generation
```bash
python generate.py
```
- [ ] Draft folder created: `drafts/{timestamp}/`
- [ ] `story.json` present with fields: `title`, `moral`, `category`, `subcategory`, `topic`, `voice`, `schema_version: 2`, `scenes`
- [ ] Telugu text uses everyday spoken style (not "గలదు", "విలవిలలాడుచున్నది" etc.)
- [ ] All `image_prompt` fields contain all 5 layers (character lock, world lock, style lock visible)
- [ ] Quality score printed ≥ 7.0
- [ ] Audio files: `audio/scene1.mp3` … `sceneN.mp3` all present
- [ ] Images: `images/scene1.png` … present (some may be missing due to quota — check `logs/image_failures.log`)
- [ ] Log written to `logs/generation_YYYYMMDD.log`

---

## 2. Draft workflow

### Preview
```bash
python preview_draft.py {timestamp}
```
- [ ] Server starts on http://localhost:8000
- [ ] Story loads in browser, slideshow visible
- [ ] Audio plays on each scene
- [ ] Images display correctly (no broken images for generated scenes)
- [ ] Swipe/tap navigation works
- [ ] Moral screen appears after last scene

### Promote
```bash
python promote.py {timestamp}
```
- [ ] Story moved from `drafts/` to `stories/{timestamp}/`
- [ ] `stories/index.json` updated with new story at top
- [ ] `sitemap.xml` regenerated
- [ ] Story visible on http://localhost:8000 homepage

### Reject
```bash
python reject.py {timestamp}
```
- [ ] `drafts/{timestamp}/` folder deleted
- [ ] `stories/index.json` unchanged

---

## 3. Balancer

After promoting a few stories:
```bash
python generate.py --dry-run
```
- [ ] Category distribution spreads across all 8 categories over time
- [ ] Subcategory distribution spreads within each category
- [ ] No topic is repeated (already-used topics skipped)

---

## 4. Index page (index.html)

Open the site in a browser (or run `python -m http.server 8000`).

### Load
- [ ] Splash screen shows and fades out
- [ ] Stories load from `stories/index.json`
- [ ] Hero banner shows latest story title, moral, thumbnail
- [ ] Category counts update correctly
- [ ] Recent stories row shows up to 8 latest
- [ ] All stories grid shows all stories

### Search
- [ ] Click 🔍 icon — search bar slides open
- [ ] Type a Telugu word — grid filters in real time (title + moral match)
- [ ] Type something with no match — "ఈ విభాగంలో కథలు లేవు" shown
- [ ] Clear search input → all stories shown again
- [ ] Click ✕ → search bar closes, full list restored

### Category filter
- [ ] Click a category pill → grid filters to that category
- [ ] Subcategory chips appear below the pills
- [ ] Click a subcategory chip → grid filters further
- [ ] "అన్నీ" chip resets to full category
- [ ] Click "అన్నీ" pill → all stories, subcategory row hides

### Lazy loading
- [ ] Open DevTools → Network tab → filter by `img`
- [ ] Images below the fold only load when scrolled into view

### Favorites link
- [ ] ♡ in header links to `favorites.html`

---

## 5. Story page (story.html)

Open any story: `story.html?id={timestamp}`

### Playback
- [ ] Scene 1 image loads (correct extension: .jpg for old stories, .png for new)
- [ ] Telugu text displays
- [ ] Audio auto-plays after 500ms
- [ ] Progress bar advances
- [ ] Dots update to show current scene
- [ ] Swipe left → next scene
- [ ] Swipe right → previous scene
- [ ] Tap → play/pause toggle
- [ ] Arrow keys (←/→) navigate scenes
- [ ] Last scene → moral screen appears

### Moral screen
- [ ] Title and moral display correctly
- [ ] Share button (📤 పంచుకోండి) appears
  - On mobile: native share sheet opens
  - On desktop (no Web Share API): WhatsApp link opens
- [ ] Related stories section shows 1–3 story cards
- [ ] Clicking a related story card navigates to it
- [ ] "← అన్ని కథలు" button returns to index

### Favorite button
- [ ] ♡ visible in top bar
- [ ] Click → becomes ♥ (orange), story saved to `localStorage`
- [ ] Refresh page → ♥ state persists
- [ ] Click again → back to ♡, removed from localStorage

### JSON-LD
- [ ] Open DevTools → Elements → `<head>`
- [ ] `<script type="application/ld+json">` present with story title and date

### Audio preload
- [ ] Open DevTools → Network tab
- [ ] While scene 1 plays, scene 2's .mp3 should start loading

---

## 6. Favorites page (favorites.html)

- [ ] Header links back to index
- [ ] Page loads without errors
- [ ] Before favoriting anything: shows "ఇంకా ఏ కథలూ సేవ్ చేయలేదు" message
- [ ] After favoriting stories via story.html: cards appear
- [ ] Clicking a card navigates to that story
- [ ] "అన్నీ తీసివేయి" button clears all favorites (with confirm dialog)

---

## 7. PWA

Open Chrome DevTools → Application tab.

### Manifest
- [ ] Manifest detected: name "Telugu Katalu", theme color #FF6B35
- [ ] Icons show (192×192 and 512×512)
- [ ] No manifest errors

### Service Worker
- [ ] SW registered and active (status: "running")
- [ ] On second load, assets served from cache (Network tab shows "ServiceWorker")

### Offline
- [ ] Load the site, then in DevTools → Network → check "Offline"
- [ ] Reload → index.html still loads from cache
- [ ] A previously viewed story still plays (audio cached)
- [ ] New stories not yet visited show gracefully degraded (empty or stale data)

### Install prompt
- [ ] On Chrome desktop/Android: "Install" option appears in address bar or menu
- [ ] After install: app opens without browser UI

---

## 8. OG / SEO (story.html)

- [ ] `<title>` tag contains story title
- [ ] `<script type="application/ld+json">` present with correct schema
- [ ] For index.html: `og:image`, `og:title`, `og:description` updated to latest story

---

## 9. Regression checks

After any change, verify these still work:
- [ ] Splash animation plays on index.html load
- [ ] Ken Burns effect on story background image
- [ ] Audio controls (play/pause button text toggles correctly)
- [ ] All 12+ existing stories still load and play (spot-check 3)
- [ ] Old stories with `.jpg` images display correctly
- [ ] New stories with `.png` images display correctly
- [ ] `sitemap.xml` contains all story URLs after promote

---

## Quick smoke test (30 seconds)

```bash
python generate.py --dry-run   # balancer works, no crash
python -m http.server 8000     # serve locally
# Open http://localhost:8000
# → splash → hero story → click play → audio plays → swipe → moral screen → share → favorites
```
