# Story Builder App — Claude Instructions

## CSS Version Bump (MANDATORY)

`static/style.css` is cache-busted with a `?v=N` query string across all HTML files.

**Every time `static/style.css` is modified, you MUST bump the version before finishing.**

### How to bump
Run this command to replace `?v=N` with the next number across all HTML files:
```
grep -r "style\.css?v=" --include="*.html" . | head -1
# note the current version, then run:
grep -rl "style\.css?v=<current>" --include="*.html" . | xargs sed -i 's/style\.css?v=<current>/style.css?v=<next>/g'
```

Or use the bump script:
```
node scripts/bump-css-version.js
```

### Current version
`v=20`

### Files that reference the version
- `index.html`
- `story.html`
- `favorites.html`
- `story/*/index.html` (all generated story pages)

### Why
Browsers cache `style.css` aggressively. Without a version bump, existing users will see
the old styles until their cache expires — which could be days or weeks. A version bump
forces all browsers to fetch the new file immediately on next visit, with no user action needed.
User localStorage data (favorites, language preference) is unaffected by cache busting.
