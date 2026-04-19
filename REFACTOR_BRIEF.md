# Telugu Katalu — Full Project Refactor Brief

You are refactoring the existing Telugu story generation project. **READ EXISTING FILES FIRST** before making any changes. Do not make assumptions about what exists. Ask clarifying questions if anything is unclear.

## ====== CURRENT STATE (verified working April 19, 2026) ======

### Project overview
- **Name:** Telugu Katalu (తెలుగు కథలు)
- **URL:** https://telugu-kathalu.pages.dev
- **Purpose:** Auto-generate Telugu moral/folk stories with AI text, AI images, AI TTS audio
- **Hosting:** Cloudflare Pages (static, no backend runtime)
- **Environment:** Windows 11, Python 3, Git Bash, VS Code
- **Deploy flow:** Python script runs locally → generates files → `git push` → Cloudflare auto-deploys
- **Current story count:** 13 stories, all in `neeti` category (category balancer bug)

### Verified working stack (test_setup.py + test_full_story.py confirmed)
- **Auth:** Application Default Credentials via `gcloud` CLI (NO JSON key file — org policy blocks key creation)
- **Story text:** Gemini 2.5 Flash via `google-genai` package (NOT deprecated `google-generativeai`)
- **TTS:** Google Cloud TTS Chirp3 HD, voice `te-IN-Chirp3-HD-Kore` tested and working
- **Image gen:** Multi-model fallback chain. Current quota limit: 1 Imagen request/minute (account too new for increase, not eligible until ~May 2026)

### Environment variables (.env file)
GEMINI_API_KEY=AIza...
GCP_PROJECT_ID=telugu-kathalu-493805
GCP_LOCATION=us-central1
NO `GOOGLE_APPLICATION_CREDENTIALS` — ADC handles this automatically.

### Current file structure
story-builder-app/
├── generate.py              ← MAIN pipeline (to be refactored)
├── check_voices.py          ← legacy utility
├── topics.txt               ← legacy
├── index.html               ← Frontend: home/browse
├── story.html               ← Frontend: slideshow reader
├── sitemap.xml              ← auto-generated
├── robots.txt
├── .env                     ← API keys (local only, gitignored)
├── static/style.css
└── stories/
├── index.json           ← master index
└── {timestamp}/          ← one folder per story (13 of these)
├── story.json
├── audio/scene1.mp3 ... scene8.mp3
└── images/scene1.jpg ... scene8.jpg

### Current story.json schema (PRESERVE ALL FIELDS)
```json
{
  "title": "Telugu title",
  "moral": "Telugu moral",
  "main_character": "English description",
  "setting": "English setting",
  "id": "20260417_001550",
  "date": "2026-04-17",
  "category": "neeti",
  "thumbnail": "stories/.../images/scene1.jpg",
  "voice": "manan",
  "scenes": [
    { "id": 1, "text": "Telugu", "image_prompt": "English" }
  ]
}
```

## ====== PROBLEMS TO FIX ======

1. **Category balancing bug:** All 13 stories landed in `neeti`. Root cause — when multiple categories tie for minimum count, code picks `candidates[0]` (dict iteration order defaults to `neeti`). Fix with `random.choice(candidates)`.

2. **Story quality is mid (Groq + llama-3.3-70b):** Produces formal/textbook Telugu ("గలదు", "విలవిలలాడుచున్నది") instead of everyday spoken Telugu. Sometimes breaks JSON.

3. **Image generation broken (Leonardo AI):** Free credits exhausted.

4. **TTS paid (Sarvam AI):** Migrating to Google Cloud TTS Chirp3 HD (free tier generous).

5. **No subcategories:** Topics inside categories are flat. Need 3 subcategories per category.

6. **Image prompts disconnected from story beats:** Test images showed generic "crow + pot" instead of scene-specific story moments with proper emotion/action. Some images had apocalyptic/aggressive vibes unsuitable for children. MUST use 5-layer fat prompt architecture (detailed below).

7. **No search, no share, no OG tags:** Basic frontend features missing.

## ====== TARGET STACK ======

### Story generation — Gemini 2.5 Flash
- Package: `google-genai` (install: `pip install google-genai`)
- Pattern:
```python
  from google import genai
  from google.genai import types
  client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
  response = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=prompt,
      config=types.GenerateContentConfig(
          response_mime_type="application/json",
          temperature=0.75,
          top_p=0.95,
      ),
  )
  story = json.loads(response.text)
```

### TTS — Google Cloud TTS Chirp3 HD
- Package: `google-cloud-texttospeech`
- Per-category voice map (use these exact voice names):
```python
  VOICE_MAP = {
      "neeti":        "te-IN-Chirp3-HD-Kore",         # warm female, moral tales
      "panchatantra": "te-IN-Chirp3-HD-Charon",       # deep storyteller, fables
      "ramayana":     "te-IN-Chirp3-HD-Algieba",      # epic male, mythology
      "tenali":       "te-IN-Chirp3-HD-Aoede",        # animated female, wit
      "birbal":       "te-IN-Chirp3-HD-Puck",         # playful, clever tales
      "janapada":     "te-IN-Chirp3-HD-Leda",         # bright rural, folk
      "podupu":       "te-IN-Chirp3-HD-Umbriel",      # sage, riddles
      "samethalu":    "te-IN-Chirp3-HD-Vindemiatrix", # wise elder, proverbs
  }
```
- Audio config: MP3, 22050 Hz sample rate (match existing files)
- Fallback: if Chirp3 HD fails, use `te-IN-Standard-B` with `pitch=-2.0, speaking_rate=0.9`
- Chirp3 HD does NOT support pitch/speakingRate — never set those for Chirp3 voices

### Image generation — MULTI-MODEL FALLBACK CHAIN
- Package: `google-genai` (Vertex AI mode)
- **Quota constraint:** Imagen 3 limited to 1 req/min on this account (not eligible for increase until ~May 2026)
- **Try models in order:**
  1. `imagen-4.0-generate-001` (Vertex)
  2. `imagen-4.0-fast-generate-001` (Vertex)
  3. `imagen-3.0-generate-002` (Vertex)
- **Pacing:** `time.sleep(15)` between image requests (respect 1/min quota)
- **On 429 error:** wait 70 seconds and retry once
- **On safety filter block:** retry with softer prompt auto-generated by Gemini
- **Never fail pipeline on image errors** — save story + audio, log missing images to `logs/image_failures.log` for manual retry
- Pattern:
```python
  from google import genai
  from google.genai import types
  client = genai.Client(
      vertexai=True,
      project=os.getenv("GCP_PROJECT_ID"),
      location=os.getenv("GCP_LOCATION"),
  )
  response = client.models.generate_images(
      model="imagen-4.0-generate-001",
      prompt=full_prompt,
      config=types.GenerateImagesConfig(
          number_of_images=1,
          aspect_ratio="4:3",
          safety_filter_level="BLOCK_ONLY_HIGH",
          person_generation="ALLOW_ADULT",
      ),
  )
  response.generated_images[0].image.save(str(image_path))
```

## ====== DATA MODEL CHANGES ======

### New file: `categories.json`
Extract category definitions from `generate.py`. Schema:
```json
{
  "neeti": {
    "telugu_name": "నీతి కథలు",
    "emoji": "📚",
    "tone": "moral, reflective, warm",
    "age_group": "5-12",
    "subcategories": {
      "animal_morals": {
        "telugu_name": "జంతు కథలు",
        "topics": ["అహంకారి సింహం మరియు చిన్న ఎలుక", "..."]
      },
      "human_values": { "telugu_name": "మానవ విలువలు", "topics": [...] },
      "wisdom_tales": { "telugu_name": "జ్ఞాన కథలు", "topics": [...] }
    }
  }
}
```

**For all 8 categories** (neeti, panchatantra, ramayana, tenali, birbal, janapada, podupu, samethalu) propose 3 subcategories each with 6-10 topics. For `neeti`, redistribute the existing 18 topics across the 3 subcategories by theme. Show me the proposed mapping before writing the file.

### Updated story.json (additive only, backward compatible)
Add these fields:
- `subcategory` (slug, e.g., `animal_morals`)
- `topic` (Telugu title string that was used as generation seed)
- `schema_version` (integer: 2)

Keep ALL existing fields. Do NOT remove anything.

### Backfill existing 13 stories
Create `backfill_existing.py`:
- Read each story.json and stories/index.json
- Add `subcategory` (map by keyword: if title contains సింహం/కాకి/ఎలుక/కుందేలు → `animal_morals`, etc.)
- Add `topic` (use existing title)
- Add `schema_version: 2`
- Keep old voice field values (Sarvam voices) intact — don't overwrite
- Show me proposed subcategory mapping for all 13 stories BEFORE running

## ====== CRITICAL: IMAGE PROMPT ARCHITECTURE (5-LAYER FAT PROMPTS) ======

Current problem: scene image_prompts are too thin → images don't match story beats, inconsistent characters, occasional aggressive/apocalyptic vibes unsuitable for children.

**Solution:** Every image_prompt MUST include all 5 layers in order:

### Layer 1 — STORY BEAT (varies per scene)
What specific action happens + what does the character FEEL in THIS scene?
Example: "A thirsty crow stands beside a tall clay pot, beak parted, looking up at the pot with hopeful curiosity (not desperation)."

### Layer 2 — CHARACTER LOCK (IDENTICAL in every scene's prompt)
Repeat the full main_character description word-for-word in every scene's image_prompt.

### Layer 3 — WORLD LOCK (IDENTICAL in every scene's prompt)
Repeat the full setting description word-for-word in every scene's image_prompt.

### Layer 4 — MOOD & LIGHTING (varies with scene beat)
- Opening scenes: "Soft golden afternoon sunlight, warm hopeful mood"
- Problem scenes: "Diffused daylight, gentle curious mood" (NOT dark/stormy)
- Thinking scenes: "Dappled shade with quiet contemplative light"
- Action scenes: "Bright clear daylight, playful energetic mood"
- Resolution scenes: "Warm golden-hour glow, triumphant peaceful mood"

### Layer 5 — STYLE LOCK (IDENTICAL in every scene's prompt)
Exact text:
> "Hand-painted children's storybook illustration, classic Indian Chandamama and Amar Chitra Katha style, soft watercolor textures, rounded friendly shapes, warm earth-tone palette (terracotta, cream, sage green, warm ochre), clean composition with breathing space. NOT photorealistic. NOT 3D render. NOT anime. NOT dark or gritty. NO cracked earth, NO apocalyptic atmosphere, NO aggressive poses, NO spread wings unless scene is explicitly about flying, NO menacing expressions. Characters should look gentle, friendly, and age-appropriate for children 5-10."

### Character description rules (for the main_character field)
Must be detailed enough to stay consistent. Include:
- Species/age/size
- 2-3 specific physical traits (eye color, feather/fur style, body language)
- Personality expression ("gentle curious eyes", "small friendly proportions")
- End with: "Always the same character across every scene."

### Setting description rules (for the setting field)
Must anchor every scene to the same world:
- Specific region (South Indian village, forest edge, riverside)
- 3-4 named visual elements (clay pot, neem tree, mud walls, dirt path)
- Atmosphere (peaceful, dusty, lush)
- End with: "Same location across every scene."

### Director's note prefix (prepend in image_gen.py before calling Imagen)
"Children's picture book illustration for ages 5-10. Gentle, warm, peaceful tone — NO violence, NO aggressive poses, NO scary imagery. "

### In-code enforcement
In `lib/image_gen.py`, include a validator that checks every image_prompt contains: the full main_character string, the full setting string, and the Layer 5 style lock substring. If any layer is missing, auto-repair by appending the missing text before sending to Imagen. Log repairs to `logs/prompt_repairs.log`.

## ====== STORY TEXT QUALITY (Telugu) ======

Current Gemini output uses formal Telugu. Must produce everyday spoken Telugu suitable for children's audio narration.

### Telugu language rules (include in the system prompt)

రోజువారీ మాట్లాడే తెలుగు వాడండి — "గలదు", "ఉన్నది", "విలవిలలాడుచున్నది" వంటి formal forms వాడవద్దు
"అప్పుడు", "అప్పటికి", "ఇంతలో", "అట్లా" వంటి సహజ కథ-చెప్పే words వాడండి
చిన్న, స్పష్టమైన వాక్యాలు — ఒక వాక్యంలో 10-15 పదాలకు మించవద్దు
పాత్రల feelings వినిపించేలా వ్రాయండి ("అతనికి చాలా సంతోషం అయింది" వంటివి)
sandhi rules మరియు spelling ఖచ్చితంగా ఉండాలి
"మరియు" అతిగా వాడవద్దు — natural flow ఉండాలి


### Few-shot examples to include in prompt
మంచి style (use this):
"ఒకరోజు ఒక కాకి చాలా దాహంతో ఉంది. అది నీళ్ల కోసం చుట్టూ వెతికింది. కొంచెం దూరంలో ఒక కుండ కనిపించింది."
చెడ్డ style (never write like this):
"ఒకానొక సమయమందు ఒక కాకి తీవ్రమైన తృష్ణతో విలవిలలాడుచున్నది."

### Full system prompt template for lib/story_gen.py
మీరు అనుభవజ్ఞుడైన తెలుగు కథకుడు. గ్రామంలో పిల్లలకు కథలు చెప్పే తాతయ్యలా వ్రాయండి — పుస్తక భాషలో కాదు.
CATEGORY: {cat_telugu}
SUBCATEGORY: {sub_telugu}
TOPIC: {topic_telugu}
TONE: {tone}
AGE GROUP: {age_group}
SCENES: 6-8
====== TELUGU LANGUAGE RULES ======
[Insert the rules block above]
ఉదాహరణ — మంచి style:
"ఒకరోజు ఒక కాకి చాలా దాహంతో ఉంది. అది నీళ్ల కోసం చుట్టూ వెతికింది."
ఉదాహరణ — చెడ్డ style (ఇలా వ్రాయవద్దు):
"ఒకానొక సమయమందు ఒక కాకి తీవ్రమైన తృష్ణతో విలవిలలాడుచున్నది."
====== IMAGE PROMPT RULES (CRITICAL) ======
Every image_prompt MUST include ALL 5 LAYERS joined by periods:
LAYER 1 — STORY BEAT (what's happening + emotion, specific to this scene)
LAYER 2 — CHARACTER LOCK (repeat full main_character word-for-word)
LAYER 3 — WORLD LOCK (repeat full setting word-for-word)
LAYER 4 — MOOD & LIGHTING (varies by scene beat — opening/problem/thinking/action/resolution)
LAYER 5 — STYLE LOCK (exact text from style lock above)
====== CHARACTER DESCRIPTION RULES ======
main_character: 2-3 sentences, species/age/size + traits + personality expression + "Always the same character across every scene."
====== SETTING DESCRIPTION RULES ======
setting: 2-3 sentences, region + visual elements + atmosphere + "Same location across every scene."
====== OUTPUT ======
Return ONLY valid JSON, no markdown fences:
{
"title": "Telugu title (3-6 words, everyday Telugu)",
"moral": "One clear Telugu sentence, simple language",
"main_character": "Detailed English character description (2-3 sentences)",
"setting": "Detailed English setting description (2-3 sentences)",
"scenes": [
{
"id": 1,
"text": "Telugu narration (2-3 sentences, spoken style)",
"image_prompt": "LAYER1 story beat. LAYER2 character lock. LAYER3 world lock. LAYER4 mood. LAYER5 style lock."
}
]
}
TITLES TO AVOID (already used): {existing_titles_list}

### Generation config
- `temperature=0.75` (NOT 0.9 — lower = better grammar)
- `top_p=0.95`
- `response_mime_type="application/json"` (forces valid JSON)

## ====== MODULE STRUCTURE ======

Refactor `generate.py` into a thin orchestrator. Create `lib/` package:
lib/
├── init.py
├── config.py          ← loads .env, loads categories.json, constants
├── story_gen.py       ← Gemini 2.5 Flash, fat prompt assembly, 5-layer image prompt enforcement
├── image_gen.py       ← Imagen 4→3 fallback chain, director's note prefix, 429 retry, prompt validator
├── tts.py             ← Chirp3 HD per-category voice map, Standard fallback
├── balancer.py        ← Subcategory-aware least-count picker with random.choice() tiebreak, auto-expand topics via Gemini when subcategory empties
├── index_writer.py    ← Atomic update of stories/index.json + sitemap.xml
└── validator.py       ← Post-generation story quality scoring via Gemini (1-10 on grammar/depth/moral/flow), auto-reject <7

`generate.py` becomes a ~50-line orchestrator calling these modules.

## ====== DRAFT / REVIEW WORKFLOW ======

1. `generate.py` outputs new stories to `drafts/{timestamp}/` (not directly to `stories/`)
2. `drafts/` added to `.gitignore`
3. Create `preview_draft.py` — starts local HTTP server on port 8000 serving `index.html` with drafts merged in preview mode
4. Create `promote.py` — moves `drafts/{id}/` → `stories/{id}/`, merges into `stories/index.json`, regenerates `sitemap.xml`
5. Create `reject.py` — deletes draft folder
6. Usage: developer runs `generate.py`, reviews via preview server, runs `promote.py <id>` to ship

## ====== BALANCING ALGORITHM (FIX BUG) ======

```python
def pick_next_slot(categories, index_stories):
    counts = {}
    for cat_key, cat_data in categories.items():
        for sub_key in cat_data["subcategories"]:
            counts[(cat_key, sub_key)] = 0
    
    for story in index_stories:
        key = (story.get("category"), story.get("subcategory"))
        if key in counts:
            counts[key] += 1
    
    min_count = min(counts.values())
    candidates = [k for k, v in counts.items() if v == min_count]
    cat_key, sub_key = random.choice(candidates)  # ← FIX: random, not [0]
    
    sub_data = categories[cat_key]["subcategories"][sub_key]
    used_topics = {s.get("topic") for s in index_stories if s.get("topic")}
    available = [t for t in sub_data["topics"] if t not in used_topics]
    
    if not available:
        # Auto-expand topics via Gemini
        new_topics = generate_new_topics(cat_key, sub_key, categories, index_stories)
        categories[cat_key]["subcategories"][sub_key]["topics"].extend(new_topics)
        save_categories(categories)
        available = new_topics
    
    return cat_key, sub_key, random.choice(available)
```

Add a `--dry-run` flag to `generate.py` that prints which slot would be picked WITHOUT calling any APIs.

## ====== FRONTEND UPDATES (minimal, preserve existing design) ======

### Preserve (do NOT change)
- Existing splash screen, animations, Ken Burns effect
- Existing CSS in `static/style.css`
- Existing story.html slideshow structure, progress bar, audio controls
- Existing index.html layout, category pills, hero banner
- Existing folder structure

### Add to index.html
1. **Real search** — replace "Coming soon" alert with client-side filter on title + moral (case-insensitive substring match)
2. **Subcategory tabs** — when a category is selected, show subcategory filter chips (read from categories.json)
3. **OG meta tags** — inject `og:image`, `og:title`, `og:description` on pageload from latest story in index.json
4. **Lazy loading** — `<img loading="lazy">` on all story card images

### Add to story.html
1. **Share button** on completion screen using Web Share API, fallback to WhatsApp URL scheme (`whatsapp://send?text=...`)
2. **JSON-LD structured data** — inject `<script type="application/ld+json">` with Article schema
3. **Related stories** on completion — 3 random stories from same subcategory (fallback: same category)
4. **Favorites** — heart icon storing story IDs in `localStorage` key `telugu_kathalu_favorites`
5. **Preload next scene's audio** while current scene plays (reduces transition lag)

### Create favorites.html
List bookmarked stories from localStorage. Link in header.

## ====== PWA BASICS ======

1. Create `manifest.json` — name "Telugu Katalu", icons, theme color, display: standalone
2. Create `sw.js` service worker — cache-first strategy for assets, network-first for JSON
3. Register service worker in `index.html`

## ====== QUALITY VALIDATION ======

1. Integrate `lib/validator.py` into `generate.py` — after draft creation, score story via Gemini on {telugu_grammar, emotional_depth, moral_clarity, narrative_flow} each 1-10
2. Flag content safety issues
3. Stories scoring <7 average get auto-rejected, max 2 regeneration retries
4. Log all scores to `logs/validation_YYYYMMDD.log`

## ====== CONSTRAINTS (DO NOT VIOLATE) ======

- **Do not delete** the existing 13 stories — all must remain playable after refactor
- **Do not rename** files referenced by live URLs (SEO preservation)
- **Do not remove** any field from existing story.json — only add
- **Do not commit** secrets — verify `.gitignore` includes `.env`, `drafts/`, `logs/`, `__pycache__/`, `test_output/`, `*.json.key`, `gcp-key.json`
- **Windows 11 paths** — always use `pathlib.Path`, never hardcoded `\` or `/`
- **No Node.js, no build step** — pure static output
- **Every API call** has try/except, max 3 retries, clear logging
- **Idempotency** — re-running `generate.py` twice must not corrupt data
- **ADC only** — do NOT reintroduce `GOOGLE_APPLICATION_CREDENTIALS` env var (service account keys are blocked by org policy)
- **Use `google-genai`** (NOT deprecated `google-generativeai`)

## ====== REQUIREMENTS.TXT ======
google-genai
google-cloud-texttospeech
python-dotenv
requests
Pillow

Do NOT include `google-generativeai` (deprecated) or `google-cloud-aiplatform` (we use google-genai Vertex mode instead).

## ====== EXECUTION PLAN — PHASED ======

Execute ONE phase at a time. After each phase, STOP and show me:
1. List of files created/modified
2. Test commands to verify
3. Any design decisions you made
4. Wait for my approval before next phase.

### Phase 1 — Foundation (safety)
1. Read `generate.py`, `stories/index.json`, one existing story.json, `index.html`, `story.html`, `static/style.css`
2. Update `.gitignore` to include: `.env`, `drafts/`, `logs/`, `__pycache__/`, `test_output/`, `*.json.key`, `gcp-key.json`, `*.mp3` in root (keep in stories/), `test_*.py` outputs
3. Create `requirements.txt` with the packages listed above
4. Propose `categories.json` structure (8 categories × 3 subcategories × 6-10 topics) — **SHOW ME BEFORE WRITING FILE**
5. Propose subcategory mapping for 13 existing stories — **SHOW ME AS A TABLE BEFORE RUNNING BACKFILL**
6. Create `backfill_existing.py` — do NOT run yet
7. Wait for my approval

### Phase 2 — Generation pipeline
1. Create `lib/` modules (config, story_gen, image_gen, tts, balancer, index_writer, validator)
2. Rewrite `generate.py` as thin orchestrator
3. Add `--dry-run` flag
4. Do NOT run yet — show me the code

### Phase 3 — Backfill
1. Run `backfill_existing.py` on the 13 existing stories
2. Show me diff of stories/index.json before/after and one story.json before/after
3. Confirm all 13 stories still playable

### Phase 4 — Dry-run verification
1. Run `python generate.py --dry-run`
2. Should print: selected category, subcategory, topic, voice (no API calls)
3. Verify balancer picks a non-neeti category this time (because neeti has 13, others have 0)

### Phase 5 — First real generation
1. Run `python generate.py` for ONE story (goes to drafts/)
2. Verify:
   - Telugu uses everyday spoken style (not formal)
   - Audio plays correctly with correct per-category voice
   - Images present (may be missing some due to 1/min quota — log them)
   - story.json has all new fields
   - image_prompts contain all 5 layers
3. Open the draft in preview server, verify it plays correctly in existing story.html

### Phase 6 — Frontend updates
1. Add search, subcategory tabs, OG tags, lazy loading to index.html
2. Add share, JSON-LD, related stories, favorites, audio preload to story.html
3. Create favorites.html
4. Test each feature manually

### Phase 7 — PWA + Quality validation
1. Add manifest.json, sw.js
2. Integrate `lib/validator.py` into generate.py (auto-reject stories scoring <7)
3. Add logging to `logs/generation_YYYYMMDD.log`

### Phase 8 — Documentation
1. Create `TEST_PLAN.md` documenting how to verify each feature
2. Update `README.md` with new workflow (gcloud ADC setup, .env vars, categories.json editing, draft → promote workflow)
3. Create `.env.example` (no real keys, just placeholder names)

## ====== DELIVERABLES ======

After all phases:
1. Refactored `generate.py` + `lib/` package
2. `categories.json` (8 × 3 × 6+)
3. `backfill_existing.py` (one-time migration)
4. `preview_draft.py`, `promote.py`, `reject.py` (review workflow)
5. Updated `.gitignore`, `requirements.txt`, `.env.example`
6. Updated `index.html`, `story.html`, new `favorites.html`
7. `manifest.json`, `sw.js` (PWA)
8. `logs/` directory (gitignored)
9. `TEST_PLAN.md`
10. Updated `README.md`

## ====== START ======

Start with Phase 1 only. First read the existing files. Then:
1. Ask me any clarifying questions
2. Propose the categories.json structure (just the schema + topic distribution proposal)
3. Propose subcategory mapping for the 13 existing stories (show as a table)
4. Wait for my approval before writing any files

Do not run any commands or create any files until I explicitly approve your proposals.

How to use it

Open REFACTOR_BRIEF.md in VS Code
Select all (Ctrl+A) and delete everything
Paste the entire block above (between the triple-dashes)
Save (Ctrl+S)
Commit to git:

bash   git add REFACTOR_BRIEF.md
   git commit -m "Finalize refactor brief with all learnings"
   git push

In Claude Code, paste this:

   Read REFACTOR_BRIEF.md in my project root for the complete context.
   
   Start Phase 1 only. Do not proceed to Phase 2 without my approval.
   
   First:
   1. Read the files listed in Phase 1
   2. Ask me any clarifying questions you have
   3. Propose the categories.json structure (show me the 8 categories × 3 subcategories × 6-10 topics as a JSON draft)
   4. Propose the subcategory mapping for my 13 existing stories (show as a table)
   5. Wait for my approval before creating or modifying ANY files
   
   Do not run any commands or create any files until I explicitly approve your proposals.