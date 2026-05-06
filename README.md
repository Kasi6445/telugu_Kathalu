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

---

## GCP Routing, Cost Tracking, and Budget Safety

### Routing rules

All Gemini API calls route through `lib/config.py:make_client()`.  Two paths exist:

| Condition | Path | Billing |
|---|---|---|
| `GCP_PROJECT_ID` set in `.env` | **Vertex AI** (primary) | GCP project credits |
| `GCP_PROJECT_ID` absent + `ALLOW_AI_STUDIO=true` | AI Studio API key | AI Studio quota / personal billing |
| `GCP_PROJECT_ID` absent + `ALLOW_AI_STUDIO` not `true` | **RuntimeError** (safety guard) | blocked |

**Exception:** `tools/build_mythology_kb.py` intentionally uses AI Studio directly and is excluded from the guard. Google Search grounding is free on AI Studio and costs $35/1,000 queries on Vertex AI.

### $300 GCP free credit — what counts

The free trial credits (`telugu-kathalu-493805`) apply to:
- Vertex AI API calls (Gemini text, Gemini TTS preview, Imagen)
- Google Cloud Text-to-Speech (Chirp3-HD voices)
- Any other GCP service consumed through the project

They do **not** apply to:
- AI Studio API key usage (`GEMINI_API_KEY`) — that's a separate billing entity
- Calls made by `tools/build_mythology_kb.py` (intentionally on AI Studio)

### Verifying routing before a run

Every process startup prints one of these lines (check your terminal):

```
[CONFIG] Routing: Vertex AI | project=telugu-kathalu-493805 | location=us-central1
[CONFIG] Routing: AI Studio API key | ALLOW_AI_STUDIO=true
[CONFIG] WARNING: GCP_PROJECT_ID not set and ALLOW_AI_STUDIO!=true — make_client() will raise
```

For a full pre-flight check (no API calls):

```bash
python scripts/check_routing.py
```

Expected output when everything is correct:

```
  RESULT: ALL 6 checks passed — safe to run smoke test
```

### Cost tracker — schema and querying

Every API call is appended to `logs/cost_audit.jsonl` as one JSON object per line.

**Token billing (text generation):**
```json
{
  "timestamp": "2026-05-05T12:34:56Z",
  "model": "gemini-2.5-flash",
  "billing_unit": "tokens",
  "input_count": 1200,
  "output_count": 800,
  "cost_usd": 0.00236,
  "cumulative_session_usd": 0.00236,
  "stage": "narration"
}
```

**Character billing (TTS):**
```json
{
  "timestamp": "2026-05-05T12:35:02Z",
  "model": "gemini-2.5-flash-preview-tts",
  "billing_unit": "characters",
  "input_count": 2000,
  "output_count": null,
  "cost_usd": 0.030,
  "cumulative_session_usd": 0.032,
  "stage": "tts_generation"
}
```

**Grounding queries (AI Studio free tier):**
```json
{
  "timestamp": "2026-05-05T12:40:00Z",
  "model": "gemini-2.5-pro+google-search",
  "billing_unit": "grounded_queries",
  "input_count": 1,
  "output_count": null,
  "cost_usd": 0.0,
  "cumulative_session_usd": 0.032,
  "stage": "kb_research",
  "estimated_vertex_cost_usd": 0.035
}
```

**Query the log from Python:**
```python
from lib.cost_tracker import print_daily_summary
print_daily_summary()               # today
print_daily_summary("2026-05-05")  # specific date
```

**Query from the command line (PowerShell):**
```powershell
# Total spend today
Get-Content logs\cost_audit.jsonl |
  ConvertFrom-Json |
  Where-Object { $_.timestamp -like "$(Get-Date -F 'yyyy-MM-dd')*" } |
  Measure-Object cost_usd -Sum

# Cost by stage
Get-Content logs\cost_audit.jsonl | ConvertFrom-Json |
  Group-Object stage |
  Select-Object Name, @{N='Total';E={($_.Group | Measure-Object cost_usd -Sum).Sum}}
```

### TTS cost ceiling (safety guard)

`gemini-2.5-flash-preview-tts` pricing is unverified (preview model not listed on Vertex AI
pricing page). A hard session ceiling of **$1.00** fires BEFORE the API call:

```python
# lib/cost_tracker.py
TTS_PREVIEW_CEILING_USD: float = 1.00
```

If hit, the error message tells you exactly what to change and where.

### Known billing incidents and API status

| Date | Case | Status | Impact |
|---|---|---|---|
| 2026-05-06 | [70914394](https://console.cloud.google.com/support/cases) | 32-hr propagation window, resolves ~May 13 | Generative Language API disabled on `telugu-kathalu-493805` — no Gemini calls until resolved |

**Why the API is disabled (case 70914394):**
A GCP support case was opened to apply goodwill credits to the account. During the resolution
window (~3-5 business days), the Generative Language API has been disabled on project
`telugu-kathalu-493805` as part of the billing remediation process. Cloud Text-to-Speech
and other GCP APIs are unaffected.

**What is blocked until ~May 13, 2026:**
- Any Gemini API call on Vertex AI (all story generation passes, TTS preview, image generation)
- `python scripts/test_vertex_smoke.py` — Phase 4 smoke test
- `python scripts/audit_one_story.py` — Phase 5 cost audit
- `python generate.py` — full pipeline

**What still works during this window:**
- `python scripts/check_routing.py` — pre-flight validator (no API calls)
- `tools/build_mythology_kb.py` — uses AI Studio directly (separate billing entity), BUT the
  Generative Language API may also be disabled there; do not assume it works
- All local code editing, analysis, and test preparation

**When the case closes:**
1. Run `python scripts/check_routing.py` — confirm 6/6 pass
2. Run `python scripts/test_vertex_smoke.py` — Phase 4 smoke test
3. If smoke test passes, run `python scripts/audit_one_story.py` — Phase 5 cost audit

### Recovery steps if billing is misconfigured

**Symptom: charges appearing on AI Studio account instead of GCP**
1. Check startup log — should say `Routing: Vertex AI`, not `AI Studio API key`
2. Verify `GCP_PROJECT_ID` is set in `.env`
3. Run `python scripts/check_routing.py` — fix any FAIL items
4. Check that `ALLOW_AI_STUDIO` is not `true` in `.env`

**Symptom: RuntimeError "Refusing to create AI Studio client"**
1. Most likely `GCP_PROJECT_ID` was accidentally removed from `.env`
2. Restore it from `.env.example` or `gcloud config get-value project`
3. If intentionally running without GCP, set `ALLOW_AI_STUDIO=true` in `.env`

**Symptom: TTS ceiling RuntimeError during story generation**
1. You have generated a lot of TTS in one session
2. Either start a new Python process (session total resets) or temporarily raise
   `TTS_PREVIEW_CEILING_USD` in `lib/cost_tracker.py`
3. Verify the TTS pricing after the billing case closes — the $0.000015/char rate
   is an estimate for a preview model not yet listed on the official pricing page

**Symptom: ADC auth errors ("Could not automatically determine credentials")**
```bash
gcloud auth application-default login
gcloud config set project telugu-kathalu-493805
```

**Emergency: disable all Vertex AI spending immediately**
1. Remove `GCP_PROJECT_ID` from `.env` — all calls will raise RuntimeError
2. Or: in GCP console → IAM → revoke the service account / user permissions on the project
3. For TTS specifically: Cloud Console → APIs & Services → disable Cloud Text-to-Speech API
