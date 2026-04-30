"""
lib/story_gen.py — Four-pass story generation for Telugu Katalu.

Pass 1: Outline (gemini-2.5-pro)      — narrative arc design in English
Pass 2: Telugu narration (gemini-2.5-flash) — grandmother-voiced execution
Pass 3: Quality validation (gemini-2.5-pro) — strict literary scoring, retry if < 8.0
Pass 4: Translations (gemini-2.5-flash) — te-en transliteration + English translation

Pro rate limit (free tier): 2 req/min.
Defensive handling: sleep before Pro calls, 429 retry, timing log.
"""

import json
import logging
import re
import time
from datetime import datetime

from google import genai
from google.genai import types
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate as _itrans_transliterate

from lib.config import GEMINI_API_KEY, STYLE_LOCK, LOGS_DIR
from lib.voices import pick_voice

logger = logging.getLogger(__name__)


# ── Transliteration helper ────────────────────────────────────────────────────

def telugu_to_readable_english(text: str) -> str:
    """Convert Telugu script to Title Case casual English transliteration."""
    itrans = _itrans_transliterate(text, sanscript.TELUGU, sanscript.ITRANS)
    # Word-final anusvara (ం) → 'm'. Must run before the consonant-cluster rules
    # so that mid-word M (before k/g/ch/t etc.) still hits the rules below.
    result = re.sub(r'M(\s|$)', lambda m: 'm' + m.group(1), itrans)
    # Handle uppercase vowel markers and anusvara context BEFORE lowercasing
    for old, new in [
        ('Mch', 'nch'), ('MT', 'nt'), ('Mk', 'nk'), ('Mg', 'ng'),
        ('Mp', 'mp'),   ('Mb', 'mb'), ('M',  'n'),
        ('A',  'aa'),   ('I',  'ii'), ('U',  'uu'),
    ]:
        result = result.replace(old, new)
    result = result.lower()
    # Clean up non-ASCII vowel markers and remaining ITRANS artefacts
    post = [('è', 'e'), ('ò', 'o'), ('R^i', 'ri'), ('~n', 'ny'), ('~N', 'ng'), ('ii', 'i'), ('uu', 'u')]
    for old, new in post:
        result = result.replace(old, new)
    return result.title()


# ── Model constants — swap here to experiment ─────────────────────────────────
OUTLINE_MODEL    = "gemini-2.5-pro"
NARRATION_MODEL  = "gemini-2.5-flash"
VALIDATION_MODEL = "gemini-2.5-pro"

# Pro rate-limit guards (free tier: 2 req/min)
_last_pro_call_at: float = 0.0
_PRO_MIN_GAP   = 30   # if last Pro call was < 30s ago, pre-sleep
_PRO_PRESLEEP  = 35   # sleep duration before Pro call when gap is tight
_PRO_429_WAIT  = 60   # wait after 429 before one retry

_VALIDATION_THRESHOLD = 8.0   # average across all 6 dimensions

# ── Mood → lighting descriptor (used in image prompt Layer 4) ─────────────────
_MOOD_MAP = {
    "opening":    "Soft golden afternoon sunlight, warm hopeful mood.",
    "problem":    "Diffused daylight, gentle curious mood (NOT dark, NOT stormy).",
    "thinking":   "Dappled shade with quiet contemplative light.",
    "action":     "Bright clear daylight, playful energetic mood.",
    "resolution": "Warm golden-hour glow, triumphant peaceful mood.",
}


# ── Pro call wrapper: rate-limit guard + 429 retry + timing log ───────────────

def _pro_call(prompt: str, config: types.GenerateContentConfig,
              model: str = OUTLINE_MODEL) -> str:
    """Make a gemini-2.5-pro call with defensive rate limiting."""
    global _last_pro_call_at

    since_last = time.time() - _last_pro_call_at
    if since_last < _PRO_MIN_GAP:
        wait = _PRO_PRESLEEP
        logger.info(f"Pro rate guard: sleeping {wait}s (last call {since_last:.1f}s ago)")
        time.sleep(wait)

    client = genai.Client(api_key=GEMINI_API_KEY)
    t0 = time.time()
    _last_pro_call_at = t0

    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=model, contents=prompt, config=config
            )
            elapsed = time.time() - t0
            _log_timing(model, elapsed)
            return response.text

        except Exception as exc:
            err = str(exc)
            if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt == 1:
                logger.warning(f"Pro 429 on attempt 1 — waiting {_PRO_429_WAIT}s then retry")
                time.sleep(_PRO_429_WAIT)
                _last_pro_call_at = time.time()
            else:
                raise RuntimeError(f"Pro call failed (attempt {attempt}): {exc}") from exc

    raise RuntimeError("Pro call exhausted retries")


def _log_timing(model: str, elapsed: float):
    timing_log = LOGS_DIR / "api_timing.log"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(timing_log, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {model} — {elapsed:.2f}s\n")
    logger.info(f"API timing: {model} {elapsed:.2f}s")


# ── Mythology categories that require child-safe violence handling ─────────────

_MYTHOLOGY_CATEGORIES = {"ramayana", "bhagavatam"}

_MYTHOLOGY_VIOLENCE_RULE = """
CHILD-SAFE VIOLENCE RULE — MANDATORY for this mythology story (ages 5-12):
Canonical stories like Narasimha, Holika, and Rama's battles contain violence.
You MUST handle all violent moments as follows — no exceptions:

  Divine victory / destruction of evil:
    Show ONLY: the flash of divine power, the earth trembling, witnesses' awe.
    Never describe: physical tearing, burning body, blood, suffering, or dying.
    Write instead: "Justice was done." / "Evil could not stand before the Lord."

  Fire scenes (Holika, Lanka):
    Show ONLY: what the DEVOTEE felt — cool breeze, flower petals, divine light.
    For the antagonist: ONE sentence maximum — "The fire returned to its source."
    Never describe: burning, screaming, ashes, pain.

  Battle / weapon scenes:
    Show ONLY: the moment of divine intervention — the roar, the light, the silence after.
    Never describe: wounds, blood, body parts, or the act of killing.

Children must feel WONDER and DEVOTION — never fear or disgust.
The story passes safety review ONLY if no scene contains graphic physical violence.
"""


# ── Pass 1: Outline ───────────────────────────────────────────────────────────

def _pass1_outline(cat_key: str, sub_key: str, topic: str, categories: dict) -> dict:
    """Design a structured 6-8 scene narrative arc in English."""
    cat = categories[cat_key]
    sub = cat["subcategories"][sub_key]

    mythology_rule = _MYTHOLOGY_VIOLENCE_RULE if cat_key in _MYTHOLOGY_CATEGORIES else ""

    prompt = f"""\
You are designing a Telugu moral tale for children aged {cat['age_group']}.
{mythology_rule}

Topic: {topic}
Category: {cat_key} — {cat['telugu_name']}
Subcategory: {sub_key} — {sub['telugu_name']}
Tone: {cat['tone']}

Create a 6-8 scene outline with a STRONG narrative arc. Never settle for fewer than 6 scenes.
Scenes must build on each other — not be independent episodes.

Arc structure (follow strictly):
  SETUP (scenes 1-2)     : Character in their world, a normal day. Show personality through action.
  TENSION (scenes 2-3)   : A real problem appears. Stakes must be clear. Character is unsure what to do.
  STRUGGLE (scenes 3-5)  : Character tries something and it partially works or fails. Inner conflict visible.
                           This is the heart of the story — spend most scenes here.
  CLIMAX (scene N-1)     : The turning point. A decision, a realisation, an act of courage.
  RESOLUTION (scene N)   : Outcome shown through action. Moral FELT, never spoken aloud.

For each scene provide:
  scene_number      : integer starting at 1
  story_beat        : exactly what happens — one clear, active sentence
  character_emotion : what the character feels AND shows (e.g. "anxious — pacing in circles")
  child_emotion     : what the listening child will feel (e.g. "nervous for the character")
  sensory_detail    : one vivid, specific detail — sound/smell/texture/colour
                      (e.g. "the drum of rain on banana leaves", "the gritty mud between tiny paws")
  key_dialogue      : ONE line of direct speech — exactly what the character OR another character says.
                      Write it as actual spoken words, not a description.
                      (e.g. "అమ్మా! ఇది నా వల్ల కాదు!" or "నువ్వు చేయగలవు — ప్రయత్నించు!")
  scene_hook        : for all scenes EXCEPT the last — one sentence describing the unanswered question
                      or unresolved moment that makes a child desperately want to hear the next scene.
                      For the final scene write "resolution".
  characters_in_scene : array of character keys who PHYSICALLY AND VISUALLY APPEAR in this scene.
                      Allowed values: "main_character" and/or "antagonist".
                      Include "antagonist" ONLY when the antagonist character is physically
                      present and visible in this scene's action — not merely mentioned or remembered.
                      Example: ["main_character"] for solo scenes, ["main_character", "antagonist"]
                      when they share the scene.

Also provide:
  main_character    : 2-sentence English description.
                      Include: species/age/size, 2-3 specific physical traits, one personality quirk.
                      End with: "Always the same character across every scene."
  antagonist        : (INCLUDE ONLY when the story has a recurring secondary character — villain,
                      mentor, trickster, magical creature, etc. — who appears in 2 or more scenes.)
                      2-sentence English visual description.
                      Include: body type, face/hair details, exact clothing colors and style,
                      any distinctive prop or feature.
                      End with: "Always the same character across every scene."
                      OMIT this field entirely if there is no recurring secondary character.
  setting           : 2-sentence English description.
                      Include: specific Telugu region or village, 3-4 named visual elements, time of day.
                      End with: "Same location across every scene."
  moral_in_english  : one universal truth — expressed as something a 5-year-old can feel, not a rule.
                      (e.g. "When you keep trying even when scared, surprising things happen."
                       NOT "Hard work leads to success.")

Return ONLY valid JSON:
{{
  "main_character": "...",
  "antagonist": "...",
  "setting": "...",
  "moral_in_english": "...",
  "scenes": [
    {{
      "scene_number":      1,
      "story_beat":        "...",
      "character_emotion": "...",
      "child_emotion":     "...",
      "sensory_detail":    "...",
      "key_dialogue":      "...",
      "scene_hook":        "...",
      "characters_in_scene": ["main_character"]
    }}
  ]
}}"""

    logger.info("Pass 1: requesting outline from gemini-2.5-pro")
    raw = _pro_call(
        prompt,
        types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7,
            top_p=0.95,
        ),
        model=OUTLINE_MODEL,
    )
    outline = json.loads(raw)
    logger.info(f"Pass 1 OK: {len(outline['scenes'])} scenes outlined")
    return outline


# ── Pass 2: Telugu narration ──────────────────────────────────────────────────

def _pass2_telugu(outline: dict, cat_key: str, sub_key: str,
                  topic: str, categories: dict, attempt: int = 1) -> dict:
    """Convert English outline into grandmother-voiced Telugu narration."""
    cat = categories[cat_key]
    sub = cat["subcategories"][sub_key]

    # Build scene outline including dialogue and hooks
    scenes_outline = "\n".join(
        f"Scene {s['scene_number']}: {s['story_beat']}\n"
        f"  Character feels : {s['character_emotion']}\n"
        f"  Sensory detail  : {s['sensory_detail']}\n"
        f"  Key dialogue    : {s.get('key_dialogue', '')}\n"
        f"  Scene hook      : {s.get('scene_hook', '')}"
        for s in outline["scenes"]
    )

    mythology_telugu_rule = ""
    if cat_key in _MYTHOLOGY_CATEGORIES:
        mythology_telugu_rule = """
====== పౌరాణిక కథలకు ప్రత్యేక నియమం (MANDATORY) ======

దైవిక శక్తి / చెడు నాశనం అయ్యే దృశ్యాలు (Narasimha, Holika, battle scenes):
  రాయవలసినది   : భక్తుడు ఏం అనుభవించాడో — చల్లటి గాలి, పువ్వుల వర్షం, దివ్యమైన కాంతి.
                  "అదే క్షణంలో, న్యాయం జరిగింది." / "దేవుని శక్తి ముందు చెడు నిలవలేకపోయింది."
  రాయకూడనిది  : శరీరానికి హాని, నొప్పి, రక్తం, తగులబడటం, అరుపులు — ఇవి ఏమీ వద్దు.

పిల్లలు భయపడకూడదు — అద్భుతం, భక్తి, ధైర్యం అనుభవించాలి.
ఈ నియమం ఒక్క scene లో కూడా మీరలేరు. safety review లో fail అయితే story publish అవ్వదు.
======
"""

    prompt = f"""\
మీరు ఒక అనుభవజ్ఞులైన తెలుగు కథకులు. మీ మనవలు చీకట్లో మంచం మీద పడుకుని, కళ్ళు మూసుకుని, మీ కంఠంలో కథ వింటున్నారు.
మీరు పుస్తకం నుండి చదవడం లేదు — మీ మనసులో ఉన్న కథను చెప్తున్నారు.
ప్రతి వాక్యంలో ప్రేమ, ఉత్కంఠ, జీవం ఉండాలి. పిల్లలు "ఇంకా చెప్పు అమ్మమ్మా!" అని అడిగేలా వ్రాయండి.
{mythology_telugu_rule}
CATEGORY   : {cat['telugu_name']}
SUBCATEGORY: {sub['telugu_name']}
TOPIC      : {topic}
TONE       : {cat['tone']}

Story outline — follow this arc exactly, do not invent new events:
  Main character : {outline['main_character']}
  Setting        : {outline['setting']}
  Moral          : {outline['moral_in_english']}

Scenes to write:
{scenes_outline}

====== భాష నియమాలు (STRICT — ఒక్కసారి చదివి గుర్తుపెట్టుకోండి) ======

నిషేధించిన forms — ఇవి రాయవద్దు:
  "గలదు", "ఉన్నది", "చున్నది", "అగును", "విలవిలలాడుచున్నది" — formal/archaic, never use
  "మరియు" — 3 కంటే ఎక్కువసార్లు ఉపయోగించవద్దు
  "అందరూ... తెలిపారు", "అతను సంతోషపడ్డాడు" — stated emotion, never write

అనుమతించిన oral forms:
  "అప్పుడు", "ఇంతలో", "అట్లాంటప్పుడు", "చూశావా?", "తెలుసా?"
  "ఏం చేశాడంటే", "ఆ క్షణంలో", "ఒక్కసారిగా"

వాక్యాలు — max 12-15 words. Short sentences hit harder.

====== AUDIO PERFORMANCE MARKERS (CRITICAL — the text becomes spoken audio) ======

The scene text is read aloud by a voice engine. You must write text that PERFORMS well,
not just reads well on paper. Use these markers to shape the audio:

  —  (em-dash)   : dramatic mid-sentence pause. The storyteller leans in.
                   "ఆ చప్పుడు — అడవంతా ఆగిపోయింది."
                   Use 1-2 times per scene at peak tension moments.

  ... (ellipsis) : suspense pause. Child holds breath, wonders what happens next.
                   "తలుపు తెరుచుకుంది... లోపల ఏముందో ఎవరికీ తెలియదు."
                   Use once per scene, only at the highest suspense beat.

  Short standalone sentence (≤6 words, own line conceptually):
                   These land like drumbeats. Use for shock, revelation, or turning point.
                   "అతను ఒంటరిగా నిలబడ్డాడు."
                   "ఇప్పుడు ఏం చేయాలి?"

  Comma rhythm   : short phrases separated by commas create a breathing, rhythmic cadence.
                   "మెల్లగా, జాగ్రత్తగా, ఒక్కో అడుగూ వేశాడు."

  DO NOT write long sentences without any punctuation — words blur into each other.
  Every 12-15 word sentence MUST have at least one comma or em-dash breaking it.

====== ప్రతి scene కి rules ======

1. LENGTH: 5-7 sentences. This is not negotiable. Short scenes feel thin and rushed.

2. DIALOGUE (mandatory):
   Every scene MUST contain at least one line of direct speech using the key_dialogue from the outline.
   Write it exactly as spoken — inside quotes.
   Example: "ఎందుకు ఏడుస్తున్నావు?" అని ఏనుగు మెల్లగా అడిగాడు.
   NOT: ఏనుగు కారణం అడిగాడు. (This is reported speech — forbidden)

3. EMOTION THROUGH BODY + ACTION (never state emotions directly):
   The reader must INFER the feeling from what the body does or what changes.

   ANGER:
     BAD : "రావణుడికి కోపం వచ్చింది."
     GOOD: "రావణుడు సింహాసనం చేతులు పిసికాడు — వేళ్ళు తెల్లబడిపోయాయి."

   FEAR:
     BAD : "ఆ పక్షికి భయం వేసింది."
     GOOD: "ఆ పక్షి రెక్కలు ముడుచుకుపోయాయి — అది గూటిలో ఇంకా లోపలకు నక్కింది."

   JOY:
     BAD : "కుందేలుకు సంతోషం కలిగింది."
     GOOD: "కుందేలు అడవంతా పరిగెత్తింది — ఆగి ఆగి గంతులు వేస్తూ."

   SADNESS:
     BAD : "అతనికి దుఃఖం కలిగింది."
     GOOD: "అతను మాట్లాడడం మానేశాడు. భోజనం తినలేదు. ఒక్కడే కూర్చుండిపోయాడు."

4. SENSORY ANCHOR:
   Weave the sensory_detail from the outline naturally into the scene text.
   Smell, sound, texture, temperature — bring the scene alive.

5. CHILD DIRECT ADDRESS (2-3 scenes only — not every scene):
   Occasionally address the child listener directly:
   "పిల్లలూ, ఇప్పుడు ఏం జరిగిందంటే చూడండి..."
   "మీకు తెలుసా, అప్పుడు అతను ఏం చేశాడో?"
   Use sparingly — only at moments of high suspense or revelation.

6. SCENE-END HOOK (all scenes except the last):
   End every scene (except the final one) with an unanswered question or unresolved moment
   that makes the child desperately want to hear the next scene.
   Use the scene_hook from the outline as guidance.
   Example ending: "కానీ వెళ్ళే ముందు — ఒక్క పని చేయాలి. ఆ పని ఏమిటో మీకు తెలుసా?"

7. FLOW: Each scene must feel like it grows out of the previous one.
   Start scenes 2+ with a callback to the last moment of the previous scene.

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "title": "Telugu title — 3-5 natural spoken words, evocative not generic",
  "moral": "One clear Telugu sentence — warm conversational tone, NOT preachy, NOT starting with 'నీతి:'",
  "main_character": "{outline['main_character']}",
  "antagonist": "{outline.get('antagonist', '')}",
  "setting": "{outline['setting']}",
  "scenes": [
    {{
      "id":           1,
      "text":         "Telugu narration — 5-7 sentences, with dialogue, sensory detail, and scene hook",
      "image_prompt": ""
    }}
  ]
}}"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    t0 = time.time()

    for flash_attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=NARRATION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.75,
                    top_p=0.95,
                ),
            )
            elapsed = time.time() - t0
            _log_timing(NARRATION_MODEL, elapsed)
            story = json.loads(response.text)

            if not story.get("scenes"):
                raise ValueError("Pass 2 returned empty scenes")
            logger.info(
                f"Pass 2 OK (narration attempt {attempt}, flash attempt {flash_attempt}): "
                f"'{story['title']}' — {len(story['scenes'])} scenes"
            )
            return story

        except Exception as exc:
            logger.warning(f"Pass 2 flash attempt {flash_attempt} failed: {exc}")
            if flash_attempt == 3:
                raise RuntimeError("Pass 2 (Telugu narration) failed after 3 Flash attempts") from exc


# ── Pass 2.5: Narration-grounded visual extraction ───────────────────────────

def _pass2b_narration_visuals(story: dict) -> dict:
    """
    Pass 2.5 — reads each scene's actual Telugu narration and asks Gemini Flash
    to describe in English the single most important visual moment to illustrate.

    This grounds the image in what is BEING NARRATED, not in the outline's
    story_beat which may have drifted during Pass 2. The result is stored as
    scene["scene_visual"] and consumed by _assemble_image_prompts.

    One batched Flash call covers all scenes — cheap and fast.
    """
    scenes_payload = "\n\n".join(
        f"Scene {s['id']}:\n{s['text']}"
        for s in story["scenes"]
    )

    prompt = f"""\
You are extracting visual scene descriptions from a Telugu children's story.

For each scene, identify the single most important visual MOMENT to illustrate —
the peak action or emotional beat that a listener hears in the narration.

For each scene write a precise 2-sentence English visual description:
  Sentence 1: What is the character physically DOING at this moment (action, posture, movement).
  Sentence 2: One specific detail from the environment or the character's expression that
              makes this moment feel real (texture, light, object in hand, facial expression).

Rules:
  - Base description ONLY on what is explicitly in the narration — do not invent.
  - Do not name the characters — refer to them as "the boy", "the old man", "the thief" etc.
  - Do not describe the moral or outcome — describe the visible action.
  - 2 sentences maximum per scene.

Telugu story scenes:
{scenes_payload}

Return ONLY valid JSON:
[
  {{"id": 1, "scene_visual": "..."}},
  {{"id": 2, "scene_visual": "..."}}
]"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    t0 = time.time()

    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=NARRATION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            elapsed = time.time() - t0
            _log_timing(NARRATION_MODEL, elapsed)

            visuals = json.loads(response.text)
            visual_map = {v["id"]: v["scene_visual"] for v in visuals}

            for scene in story["scenes"]:
                scene["scene_visual"] = visual_map.get(scene["id"], "")

            logger.info(
                f"Pass 2.5 OK: narration-grounded visuals extracted "
                f"for {len(story['scenes'])} scenes"
            )
            return story

        except Exception as exc:
            logger.warning(f"Pass 2.5 attempt {attempt}/2 failed: {exc}")
            if attempt == 2:
                # Non-fatal: fall back to empty scene_visual — _assemble_image_prompts
                # will use the outline story_beat as before.
                logger.warning("Pass 2.5 failed — image prompts will use outline beats (fallback)")
                for scene in story["scenes"]:
                    scene.setdefault("scene_visual", "")
                return story


# ── Image prompt assembly (programmatic, deterministic) ───────────────────────

def _infer_mood(scene_idx: int, total: int) -> str:
    if scene_idx == 0:
        return "opening"
    if scene_idx == total - 1:
        return "resolution"
    if scene_idx <= max(1, total // 3):
        return "problem"
    if scene_idx >= total - 2:
        return "action"
    return "thinking"


# Patterns checked only in character_emotion (not the beat) because the beat
# describes ALL characters' actions, while emotion only describes the main character.
# Trailing space on "watches "/"observes " prevents matching "observant".
_OBSERVER_PATTERNS = [
    "watches ", "watching ", "observes ", "observing ",
    "looks on", "witness", "gaze fixed",
]


def _is_observer_scene(emotion: str, _beat: str) -> bool:
    """True when the main character is watching someone else act, not acting themselves."""
    emotion_lower = emotion.lower()
    return any(p in emotion_lower for p in _OBSERVER_PATTERNS)


def _assemble_image_prompts(story: dict, outline: dict) -> dict:
    """Build scene-specific image prompts using Pass 1 outline data.

    Stores ONLY what is unique to this scene: the action, emotion, sensory
    detail, antagonist presence, and mood lighting.

    The fixed anchors — main_character, setting, STYLE_LOCK — are added
    exactly once by image_gen._build_prompt so they never duplicate.

    For ACTION scenes  : main character is the foreground focal point.
    For OBSERVER scenes: main character watches from the side while the
                         secondary character's action fills the foreground.
    """
    outline_by_num = {s["scene_number"]: s for s in outline["scenes"]}
    total = len(story["scenes"])

    for scene in story["scenes"]:
        o = outline_by_num.get(scene["id"], {})

        # scene_visual: narration-grounded description from Pass 2.5.
        # Falls back to outline story_beat if Pass 2.5 was skipped or failed.
        scene_visual = scene.get("scene_visual", "").strip()
        beat         = o.get("story_beat", f"Scene {scene['id']} unfolds.")
        emotion      = o.get("character_emotion", "")
        mood         = _MOOD_MAP[_infer_mood(scene["id"] - 1, total)]

        # Antagonist: include ONLY in scenes where they physically appear.
        antagonist = story.get("antagonist", "")
        o_chars = o.get("characters_in_scene", ["main_character"])
        antagonist_in_scene = bool(antagonist) and "antagonist" in o_chars
        antagonist_note = f"Also in this scene: {antagonist}" if antagonist_in_scene else ""

        if scene_visual:
            # Pass 2.5 succeeded — use narration-derived visual as the scene action.
            # Observer detection still adjusts framing when relevant.
            if _is_observer_scene(emotion, beat):
                action = f"{scene_visual} The protagonist watches from the side."
            else:
                action = scene_visual
        else:
            # Fallback: use outline story_beat (pre-Pass 2.5 behaviour).
            if _is_observer_scene(emotion, beat):
                action = (
                    f"{beat} "
                    f"The main character watches from the side, expression: {emotion}."
                )
            else:
                action = f"{beat} {emotion}."

        scene["image_prompt"] = " ".join(filter(None, [action, antagonist_note, mood]))

    return story


# ── Pass 3: Quality validation ────────────────────────────────────────────────

def _pass3_validate(story: dict) -> tuple[float, dict]:
    """Score Pass 2 output with gemini-2.5-pro. Returns (average, full_result)."""
    scenes_text = "\n".join(f"Scene {s['id']}: {s['text']}" for s in story["scenes"])

    prompt = f"""\
You are a senior Telugu children's literature editor with 20 years experience.
Score this story with professional rigour — do NOT inflate scores. Be a harsh critic.

Score each dimension 1-10:

1. grandmother_authenticity
   Does it sound like a real grandparent telling a bedtime story, or like a school textbook?
   10 = pure oral warmth — you can hear the voice, feel the pauses, sense the love
    8 = mostly warm, a few stiff phrases
    6 = half oral, half written — inconsistent register
    4 = mostly formal, cold
    1 = textbook prose with no warmth at all

2. emotional_depth
   Feelings shown through body language, action, dialogue — never stated directly?
   10 = fully embodied throughout ("అతను వణికిపోయాడు — ఆ శబ్దం అతన్ని ఆపింది")
    8 = mostly shown, 1-2 small slips
    6 = roughly half shown, half stated
    4 = mostly stated ("అతనికి సంతోషం కలిగింది")
    1 = all emotions reported, never felt

3. dialogue_richness
   Does each character have a distinct voice? Is dialogue natural and scene-specific?
   Does at least every scene have one direct speech line?
   10 = every scene has vivid, character-specific dialogue that advances the story
    8 = most scenes have dialogue, feels natural
    6 = some scenes have dialogue, quality varies
    4 = little to no dialogue — story feels like a report
    1 = zero dialogue anywhere

4. grammar_correctness
   Correct sandhi, natural spoken Telugu, zero archaic endings (-గలదు, -చున్నది, -ఉన్నది)?
   10 = flawless colloquial Telugu, feels native
    8 = nearly flawless, 1-2 minor issues
    6 = a few errors or 1-2 archaic forms
    4 = multiple errors or consistently archaic
    1 = broken grammar throughout

5. narrative_arc
   Does tension genuinely build across 6+ scenes and resolve without a sermon?
   Is there a real struggle (character tries and fails before succeeding)?
   10 = compelling arc, moral emerges from events — children will beg to hear it again
    8 = solid arc, minor pacing issues
    6 = arc present but tension is weak or resolution is rushed
    4 = flat — series of events, not a story
    1 = no arc, preachy, or moral explicitly stated by narrator

6. child_engagement
   Would a 6-year-old listening in the dark stay wide awake until the end?
   Are there suspense hooks? Direct child address? Moments of wonder?
   10 = irresistible — hooks at every scene end, child directly included in the story
    8 = engaging throughout, minor dull spots
    6 = interesting in parts but loses attention in the middle
    4 = mostly dull — child would fall asleep
    1 = no engagement devices at all

Scoring discipline:
  9-10 = publish immediately, this is award-worthy
  8    = you would read this to your own child without hesitation
  7    = acceptable but forgettable — one more revision needed
  6    = needs significant work
  Below 6 = rewrite from scratch

STORY:
Title : {story.get('title', '')}
Moral : {story.get('moral', '')}
Scenes: {len(story.get('scenes', []))}

{scenes_text}

Return ONLY valid JSON:
{{
  "grandmother_authenticity": <1-10>,
  "emotional_depth":          <1-10>,
  "dialogue_richness":        <1-10>,
  "grammar_correctness":      <1-10>,
  "narrative_arc":            <1-10>,
  "child_engagement":         <1-10>,
  "average":                  <float, mean of all 6 scores>,
  "weakest_dimension":        "<name of the lowest-scoring dimension>",
  "notes": "3-4 sentences: what works, what is the single most important fix to reach 9+"
}}"""

    logger.info("Pass 3: requesting validation from gemini-2.5-pro")
    raw = _pro_call(
        prompt,
        types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
        model=VALIDATION_MODEL,
    )
    result = json.loads(raw)
    dims = [
        "grandmother_authenticity",
        "emotional_depth",
        "dialogue_richness",
        "grammar_correctness",
        "narrative_arc",
        "child_engagement",
    ]
    avg = sum(result.get(d, 0) for d in dims) / len(dims)
    result["average"] = round(avg, 2)

    status = "PASS" if avg >= _VALIDATION_THRESHOLD else "FAIL"
    logger.info(f"Pass 3 {status}: avg={avg:.2f} — {result.get('notes','')}")
    return avg, result


# ── Pass 4: Translations ─────────────────────────────────────────────────────

def _pass4_translations(story: dict) -> dict:
    """Add _te_en (transliteration) and _en (English) fields to story and scenes.

    Transliteration is fast and local.
    English translation is a single batched Gemini Flash call.
    """
    # Transliteration — no API, instant
    story['title_te_en'] = telugu_to_readable_english(story['title'])
    story['moral_te_en'] = telugu_to_readable_english(story['moral'])
    for scene in story['scenes']:
        scene['text_te_en'] = telugu_to_readable_english(scene['text'])

    # English translation — one batched Flash call
    payload = {
        'title': story['title'],
        'moral': story['moral'],
        'scenes': [{'id': s['id'], 'text': s['text']} for s in story['scenes']],
    }

    prompt = f"""\
Translate this Telugu children's story to natural English.
- Simple, clear English for children aged 5-12
- Preserve emotional tone and storytelling warmth
- Don't add or remove meaning
- Keep character names as-is
- Return ONLY valid JSON, no notes or markdown

Input JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return exactly this structure:
{{
  "title_en": "...",
  "moral_en": "...",
  "scenes": [{{"id": 1, "text_en": "..."}}]
}}"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    t0 = time.time()
    response = client.models.generate_content(
        model=NARRATION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.3,
        ),
    )
    elapsed = time.time() - t0
    _log_timing(NARRATION_MODEL, elapsed)

    translations = json.loads(response.text)
    story['title_en'] = translations['title_en']
    story['moral_en'] = translations['moral_en']

    scene_map = {s['id']: s for s in story['scenes']}
    for t_scene in translations.get('scenes', []):
        if t_scene['id'] in scene_map:
            scene_map[t_scene['id']]['text_en'] = t_scene['text_en']

    logger.info(f"Pass 4 OK: translations added — '{story['title_en']}'")
    return story


# ── Public API ────────────────────────────────────────────────────────────────

def generate_story(cat_key: str, sub_key: str, topic: str,
                   categories: dict, story_index: list) -> dict:
    """Full 3-pass pipeline. Returns story dict ready for TTS + image gen.

    story_index             : list of story dicts from index.json (used for voice variety + duplicate title check)
    story["voice"]          : selected Chirp3-HD voice name
    story["quality_score"]  : Pass 3 average (float)
    story["quality_warning"]: True if score < 8.0 after all retries (needs review)
    story["image_prompt"]   : pre-assembled 5-layer prompt per scene
    """
    existing_titles = [s.get("title", "") for s in story_index]

    # ── Pass 1: Outline (Pro) ─────────────────────────────────────────────────
    outline = _pass1_outline(cat_key, sub_key, topic, categories)

    # Carry antagonist from outline into Pass 2 so _assemble_image_prompts can use it
    if outline.get("antagonist"):
        logger.info(f"Antagonist locked: {outline['antagonist'][:80]}...")

    # ── Passes 2 + 3: narrate → validate → retry up to 2× ────────────────────
    quality_warning = False
    final_story     = None
    final_score     = 0.0
    final_scores    = {}

    for attempt in range(1, 4):   # 1 initial + 2 retries
        telugu_story = _pass2_telugu(outline, cat_key, sub_key, topic, categories, attempt)

        # Pass 2.5: extract narration-grounded visual descriptions for each scene.
        # These drive image generation so images match exactly what is narrated.
        telugu_story = _pass2b_narration_visuals(telugu_story)

        # Assemble image prompts using Pass 2.5 visuals (falls back to outline beats)
        telugu_story = _assemble_image_prompts(telugu_story, outline)

        score, score_detail = _pass3_validate(telugu_story)

        if score >= _VALIDATION_THRESHOLD:
            final_story  = telugu_story
            final_score  = score
            final_scores = score_detail
            logger.info(f"Story accepted on attempt {attempt} (score={score:.2f})")
            break

        logger.warning(
            f"Quality {score:.2f} < {_VALIDATION_THRESHOLD} "
            f"(attempt {attempt}/3) — "
            f"{score_detail.get('notes', '')}"
        )
        if attempt == 3:
            # Accept with warning rather than abort
            final_story     = telugu_story
            final_score     = score
            final_scores    = score_detail
            quality_warning = True
            logger.warning("All 3 attempts below threshold — saving with quality_warning=True")

    # ── Pick voice (needs main_character from outline for gender bias) ────────
    voice = pick_voice(cat_key, sub_key, final_story, story_index)
    final_story["voice"] = voice

    # ── Attach quality metadata ───────────────────────────────────────────────
    final_story["quality_score"]  = final_score
    final_story["quality_scores"] = final_scores
    if quality_warning:
        final_story["quality_warning"] = True

    # ── Pass 4: Translations ──────────────────────────────────────────────────
    final_story = _pass4_translations(final_story)

    return final_story
