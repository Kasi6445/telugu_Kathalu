# Telugu Katalu — తెలుగు కథలు

Auto-generated Telugu moral and folk stories with AI text, AI images, and AI TTS audio.

**Live site:** https://telugukathalu.in  
**Hosting:** Cloudflare Pages (static, no backend)  
**Deploy flow:** Python runs locally → generates files → `git push` → auto-deploys

---

## Prerequisites

- Python 3.10+
- `gcloud` CLI installed and authenticated
- A Google Cloud project with Vertex AI and Cloud TTS APIs enabled

---

## First-time setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd story-builder-app
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in GEMINI_API_KEY and GCP_PROJECT_ID
```

### 3. Authenticate with Google Cloud (ADC)

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

> **Do not** create or use a service account JSON key — org policy blocks key creation on this account. ADC handles all auth automatically.

### 4. Verify setup

```bash
python -c "from lib.config import load_categories; print('OK', len(load_categories()), 'categories')"
```

---

## Generating stories

### Dry run (no API calls)

```bash
python generate.py --dry-run
```

Prints which category/subcategory/topic would be picked next without calling any APIs.

### Generate one story

```bash
python generate.py
```

The story is saved to `drafts/{timestamp}/` — **not** published yet.

Output:
```
📂 Category   : 📚 నీతి కథలు
📁 Subcategory : జంతు కథలు
📖 Topic       : అహంకారి సింహం మరియు చిన్న ఎలుక
🎙️  Voice       : te-IN-Chirp3-HD-Kore
📊 Quality score: 8.25/10

   Preview : python preview_draft.py 20260420_141000
   Promote : python promote.py 20260420_141000
   Reject  : python reject.py 20260420_141000
```

### Review a draft

```bash
python preview_draft.py 20260420_141000
# Opens http://localhost:8000 — browse to the draft story and check it plays correctly
```

### Publish a draft

```bash
python promote.py 20260420_141000
git add stories/ sitemap.xml
git commit -m "Add story: <title>"
git push
```

Cloudflare Pages auto-deploys within ~60 seconds.

### Reject a draft

```bash
python reject.py 20260420_141000
```

---

## Project structure

```
story-builder-app/
├── generate.py              # Main pipeline orchestrator (~100 lines)
├── preview_draft.py         # Local preview server (port 8000)
├── promote.py               # Move draft → stories/, update index
├── reject.py                # Delete a draft
├── backfill_existing.py     # One-time schema v2 migration (already run)
├── categories.json          # 8 categories × 3 subcategories × topics
├── requirements.txt
├── .env                     # Local only — never commit
├── .env.example             # Template for .env
│
├── lib/                     # Generation pipeline modules
│   ├── config.py            # Load .env, categories.json, constants
│   ├── story_gen.py         # Gemini 2.5 Flash story generation
│   ├── image_gen.py         # Imagen 4→3 fallback chain
│   ├── tts.py               # Google Cloud TTS Chirp3 HD
│   ├── balancer.py          # Subcategory-aware story slot picker
│   ├── index_writer.py      # Atomic stories/index.json + sitemap update
│   └── validator.py         # Gemini quality scorer (auto-reject <7/10)
│
├── index.html               # Home page (browse + search)
├── story.html               # Slideshow story reader
├── favorites.html           # Bookmarked stories
├── manifest.json            # PWA manifest
├── sw.js                    # Service worker (offline support)
├── static/
│   ├── style.css
│   ├── icon-192.png         # PWA icon
│   └── icon-512.png         # PWA icon
│
├── stories/
│   ├── index.json           # Master story index
│   └── {timestamp}/
│       ├── story.json
│       ├── audio/scene1.mp3 … scene8.mp3
│       └── images/scene1.png … scene8.png
│
├── drafts/                  # Unpublished drafts (gitignored)
└── logs/                    # Generation logs (gitignored)
```

---

## Editing categories and topics

Open `categories.json`. Each category has 3 subcategories with a list of topics. To add a topic:

```json
"neeti": {
  "subcategories": {
    "animal_morals": {
      "telugu_name": "జంతు కథలు",
      "topics": [
        "existing topic",
        "your new topic here"   ← add here
      ]
    }
  }
}
```

The balancer picks the least-used subcategory automatically. If a subcategory runs out of topics, Gemini auto-generates more.

---

## Voice map (per category)

| Category     | Voice                        | Character     |
|--------------|------------------------------|---------------|
| neeti        | te-IN-Chirp3-HD-Kore         | Warm female   |
| panchatantra | te-IN-Chirp3-HD-Charon       | Deep storyteller |
| ramayana     | te-IN-Chirp3-HD-Algieba      | Epic male     |
| tenali       | te-IN-Chirp3-HD-Aoede        | Animated female |
| birbal       | te-IN-Chirp3-HD-Puck         | Playful       |
| janapada     | te-IN-Chirp3-HD-Leda         | Bright rural  |
| podupu       | te-IN-Chirp3-HD-Umbriel      | Sage          |
| samethalu    | te-IN-Chirp3-HD-Vindemiatrix | Wise elder    |

---

## Image generation quota

Imagen is limited to **1 request/minute** on this account (not eligible for increase until ~May 2026). The pipeline sleeps 15s between images and retries on 429. Missing images are logged to `logs/image_failures.log` and don't block the story.

---

## Quality validation

Every generated story is automatically scored by Gemini on:
- `telugu_grammar` — everyday spoken Telugu, not formal/archaic
- `emotional_depth` — character feelings, emotional arc
- `moral_clarity` — lesson clear and age-appropriate
- `narrative_flow` — scene-to-scene coherence

Stories averaging **< 7/10** are auto-rejected (up to 2 retries). Scores are logged to `logs/generation_YYYYMMDD.log`.

---

## Logs

| File | Contents |
|------|----------|
| `logs/generation_YYYYMMDD.log` | Full pipeline log per day |
| `logs/image_failures.log` | Scenes where image generation failed |
| `logs/prompt_repairs.log` | Image prompts auto-repaired (missing layers) |
| `logs/backfill_decisions.log` | One-time schema v2 migration record |
| `logs/promote_YYYYMMDD.log` | Draft promotion history |

---

## Deployment

Push to `main` → Cloudflare Pages auto-deploys.

```bash
git add .
git commit -m "Add N new stories"
git push origin main
```

No build step. Output is pure static files.
