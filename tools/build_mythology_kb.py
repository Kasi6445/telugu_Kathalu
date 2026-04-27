"""
tools/build_mythology_kb.py — One-time script to build the mythology knowledge base.

Uses Gemini 2.5 Pro with Google Search grounding to research canonical Hindu mythology
characters, weapons, and scenes. Output is saved to research_output/mythology_kb_raw.json
for HUMAN REVIEW before being incorporated into lib/mythology_knowledge.py.

Usage:
  python tools/build_mythology_kb.py --chars Rama Vali
  python tools/build_mythology_kb.py --all
  python tools/build_mythology_kb.py --chars Rama Vali --scenes

Default (no flags): runs Rama and Vali only (Phase A start).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from google.genai import types

from lib.config import GEMINI_API_KEY

# ── Output paths ──────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).parent.parent
OUTPUT_DIR     = BASE_DIR / "research_output"
OUTPUT_FILE    = OUTPUT_DIR / "mythology_kb_raw.json"

# ── Rate limiting (Pro free tier: 2 req/min) ─────────────────────────────────

_last_pro_call_at: float = 0.0

def _pro_grounded_call(client: genai.Client, prompt: str) -> tuple[str, list[dict]]:
    """Call Gemini 2.5 Pro with Google Search grounding. Returns (text, sources)."""
    global _last_pro_call_at

    since_last = time.time() - _last_pro_call_at
    if since_last < 30:
        wait = 35 - since_last
        print(f"  [rate guard] sleeping {wait:.0f}s …")
        time.sleep(wait)

    _last_pro_call_at = time.time()

    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[google_search_tool],
                    temperature=0.2,
                ),
            )

            # Extract grounding sources
            sources = []
            try:
                gm = response.candidates[0].grounding_metadata
                if gm and hasattr(gm, "grounding_chunks") and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, "web") and chunk.web:
                            sources.append({
                                "url":   chunk.web.uri,
                                "title": getattr(chunk.web, "title", ""),
                            })
            except (IndexError, AttributeError):
                pass  # grounding metadata not always present

            return response.text, sources

        except Exception as exc:
            err = str(exc)
            if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt == 1:
                print(f"  [429] rate limited — waiting 65s …")
                time.sleep(65)
                _last_pro_call_at = time.time()
            else:
                raise RuntimeError(f"Pro call failed (attempt {attempt}): {exc}") from exc

    raise RuntimeError("Pro call exhausted retries")


def _extract_json(text: str) -> dict:
    """Extract JSON from a Gemini response that may include markdown fences."""
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(text)


# ── Character research ────────────────────────────────────────────────────────

CHARACTER_PROMPT = """\
You are a Hindu mythology scholar with expertise in canonical Valmiki Ramayana,
Vyasa Mahabharata, Srimad Bhagavatam, and classical Telugu iconography.

Using Google Search, research the Hindu mythological figure: **{name}**

Pull from reputable sources: Valmiki Ramayana translations (Gita Press, IIT Kanpur),
Hindupedia, Wikipedia (mythology articles), sacred-texts.com, established temple websites,
scholarly works on Indian iconography.

Compile CANONICAL iconographic and narrative details. Be specific and cite sources.

Provide a structured analysis with the following fields:

1. telugu_name: Name in Telugu script (e.g., "రాముడు")
2. sanskrit_name: Name in Devanagari (e.g., "रामः")
3. physical_appearance:
   - skin_color: Exact canonical description (e.g., "श्यामल — dark blue like rain cloud, NOT light blue, NOT green")
   - height_build: Typical depiction
   - hair: Style, color, adornments
   - eyes: Shape, color, expression
   - notable_features: Any distinctive marks
4. clothing_and_ornaments:
   - typical_garment: What they wear
   - crown_or_headdress: If any
   - jewelry: Specific ornaments
   - footwear: If mentioned
5. iconographic_markers:
   - primary_weapon: Exact name and description
   - secondary_items: Other held objects
   - mount_or_vehicle: If any (vahana)
   - typical_posture: Standing, seated, etc.
   - mudras: Hand gestures if relevant
6. personality_traits: 3-5 traits consistently depicted across traditions
7. common_ai_illustration_mistakes:
   - List 5-8 specific errors AI systems make when depicting this character
   - Be very specific (e.g., "AI often shows Rama with a green skin tone — wrong, must be dark blue/श्याम")
8. canonical_scenes:
   - List 3-5 most important scenes featuring this character
   - For each: scene_name, what_happens, visual_key_detail
9. regional_variations:
   - Note any Telugu/Andhra-specific iconographic traditions vs. general North Indian
10. sources_consulted_in_research: List the specific URLs or texts you found and used

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "character": "{name}",
  "telugu_name": "...",
  "sanskrit_name": "...",
  "physical_appearance": {{
    "skin_color": "...",
    "height_build": "...",
    "hair": "...",
    "eyes": "...",
    "notable_features": "..."
  }},
  "clothing_and_ornaments": {{
    "typical_garment": "...",
    "crown_or_headdress": "...",
    "jewelry": "...",
    "footwear": "..."
  }},
  "iconographic_markers": {{
    "primary_weapon": "...",
    "secondary_items": "...",
    "mount_or_vehicle": "...",
    "typical_posture": "...",
    "mudras": "..."
  }},
  "personality_traits": ["...", "..."],
  "common_ai_illustration_mistakes": ["...", "..."],
  "canonical_scenes": [
    {{
      "scene_name": "...",
      "what_happens": "...",
      "visual_key_detail": "..."
    }}
  ],
  "regional_variations": "...",
  "sources_consulted_in_research": ["...", "..."]
}}"""


def research_character(client: genai.Client, name: str) -> dict:
    print(f"\n  Researching character: {name}")
    prompt = CHARACTER_PROMPT.format(name=name)

    text, grounding_sources = _pro_grounded_call(client, prompt)

    try:
        data = _extract_json(text)
    except json.JSONDecodeError:
        # Fallback: store raw text for manual review
        print(f"  [warn] JSON parse failed for {name} — storing raw text")
        data = {"character": name, "_raw_text": text, "_parse_error": True}

    data["_grounding_sources"] = grounding_sources
    data["_researched_at"] = datetime.now().isoformat()

    source_count = len(grounding_sources)
    print(f"  Done: {name} — {source_count} grounding source(s) found")
    if grounding_sources:
        for s in grounding_sources[:3]:
            print(f"    • {s.get('title', '(no title)')} — {s.get('url', '')[:80]}")
        if source_count > 3:
            print(f"    … and {source_count - 3} more")

    return data


# ── Weapon research ───────────────────────────────────────────────────────────

WEAPON_PROMPT = """\
You are a Hindu mythology and iconography scholar.

Using Google Search, research the weapon/object: **{name}**
from Hindu mythology (Ramayana / Mahabharata / Puranas).

Pull from: Valmiki Ramayana translations, Hindupedia, Wikipedia, sacred-texts.com,
scholarly iconography texts.

Provide canonical details:

1. Sanskrit/Telugu name and meaning
2. Physical description: exact appearance, material, size, color
3. Who wields it and in which tradition
4. How it is depicted in classical Indian art (Tanjore paintings, temple sculptures)
5. Common AI illustration mistakes (5 specific errors)
6. Notable scenes where it appears
7. Sources consulted

Return ONLY valid JSON:
{{
  "weapon": "{name}",
  "sanskrit_name": "...",
  "telugu_name": "...",
  "meaning": "...",
  "physical_description": "...",
  "wielded_by": "...",
  "art_depiction": "...",
  "common_ai_mistakes": ["...", "..."],
  "notable_scenes": ["...", "..."],
  "sources_consulted_in_research": ["...", "..."]
}}"""


def research_weapon(client: genai.Client, name: str) -> dict:
    print(f"\n  Researching weapon: {name}")
    prompt = WEAPON_PROMPT.format(name=name)
    text, grounding_sources = _pro_grounded_call(client, prompt)

    try:
        data = _extract_json(text)
    except json.JSONDecodeError:
        print(f"  [warn] JSON parse failed for {name} — storing raw text")
        data = {"weapon": name, "_raw_text": text, "_parse_error": True}

    data["_grounding_sources"] = grounding_sources
    data["_researched_at"] = datetime.now().isoformat()
    print(f"  Done: {name} — {len(grounding_sources)} grounding source(s)")
    return data


# ── Scene research ────────────────────────────────────────────────────────────

SCENE_PROMPT = """\
You are a Hindu mythology scholar specialising in Valmiki Ramayana and
Vyasa Mahabharata canonical texts.

Using Google Search, research this specific scene: **{name}**

Pull from: Valmiki Ramayana (Gita Press, IIT Kanpur translation), Hindupedia,
Wikipedia, sacred-texts.com, scholarly translations.

Provide the canonical account with pinpoint accuracy:

1. Source text and chapter/kanda reference (e.g., "Kishkindha Kanda, Sargas 11-18")
2. What happens — step by step, in canonical order
3. Key factual details that are commonly confused or misrepresented
4. Visual scene description: what would a witness see?
5. Dialogue — any key lines spoken (in Sanskrit if known, with translation)
6. Why this scene matters narratively and spiritually
7. Common misconceptions or inaccuracies in popular retellings
8. Sources consulted

Return ONLY valid JSON:
{{
  "scene": "{name}",
  "source_text": "...",
  "chapter_reference": "...",
  "canonical_sequence": ["step 1", "step 2", "..."],
  "key_facts_often_confused": ["...", "..."],
  "visual_description": "...",
  "key_dialogue": [{{"speaker": "...", "words": "...", "translation": "..."}}],
  "narrative_significance": "...",
  "common_misconceptions": ["...", "..."],
  "sources_consulted_in_research": ["...", "..."]
}}"""


def research_scene(client: genai.Client, name: str) -> dict:
    print(f"\n  Researching scene: {name}")
    prompt = SCENE_PROMPT.format(name=name)
    text, grounding_sources = _pro_grounded_call(client, prompt)

    try:
        data = _extract_json(text)
    except json.JSONDecodeError:
        print(f"  [warn] JSON parse failed for {name} — storing raw text")
        data = {"scene": name, "_raw_text": text, "_parse_error": True}

    data["_grounding_sources"] = grounding_sources
    data["_researched_at"] = datetime.now().isoformat()
    print(f"  Done: {name} — {len(grounding_sources)} grounding source(s)")
    return data


# ── Full character / weapon / scene sets ─────────────────────────────────────

ALL_CHARACTERS = [
    "Rama", "Sita", "Lakshmana", "Hanuman",
    "Vali", "Sugriva", "Ravana", "Bharata",
    "Krishna", "Arjuna", "Bhima", "Yudhishthira",
    "Ganesha", "Shiva", "Parvati", "Lakshmi",
]

ALL_WEAPONS = [
    "Kodanda (Rama's bow)",
    "Sudarshana Chakra",
    "Gada (Hanuman's mace)",
    "Trishul (Shiva's trident)",
    "Pinaka (Shiva's bow)",
]

ALL_SCENES = [
    "Vali Sugriva fight in Kishkindha — why Rama shot Vali from behind a tree",
    "Hanuman crossing the ocean to Lanka",
    "Krishna lifting Govardhan hill",
    "Rama crossing the setu bridge to Lanka",
    "Ravana abducting Sita in Panchavati",
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build mythology knowledge base via Gemini grounding")
    parser.add_argument("--chars",   nargs="+", metavar="CHAR",  help="Characters to research")
    parser.add_argument("--weapons", nargs="+", metavar="WPNS",  help="Weapons to research")
    parser.add_argument("--scenes",  action="store_true",         help="Research default scene set")
    parser.add_argument("--all",     action="store_true",         help="Research everything (takes ~45 min)")
    args = parser.parse_args()

    # Default: Rama + Vali only
    chars_to_research   = args.chars   if args.chars   else (ALL_CHARACTERS if args.all else ["Rama", "Vali"])
    weapons_to_research = args.weapons if args.weapons else (ALL_WEAPONS    if args.all else [])
    scenes_to_research  = ALL_SCENES   if (args.scenes or args.all) else []

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set. Check your .env file.")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)

    print("=" * 60)
    print("Mythology KB Builder — Gemini 2.5 Pro + Google Search")
    print("=" * 60)
    print(f"Characters : {chars_to_research}")
    print(f"Weapons    : {weapons_to_research or '(none)'}")
    print(f"Scenes     : {['yes — ' + str(len(scenes_to_research)) + ' scenes'] if scenes_to_research else ['(none)']}")
    print(f"Output     : {OUTPUT_FILE}")
    print()

    # Load existing output if present (resume support)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            kb = json.load(f)
        print(f"Resuming from existing output ({len(kb.get('characters', {}))} chars, "
              f"{len(kb.get('weapons', {}))} weapons, {len(kb.get('scenes', {}))} scenes already done)\n")
    else:
        kb = {"characters": {}, "weapons": {}, "scenes": {}, "_meta": {}}

    kb["_meta"]["last_run"] = datetime.now().isoformat()
    kb["_meta"]["note"] = "RAW RESEARCH OUTPUT — requires human review before use in lib/mythology_knowledge.py"

    # ── Characters ───────────────────────────────────────────────────────────
    for name in chars_to_research:
        key = name.lower().replace(" ", "_")
        if key in kb["characters"]:
            print(f"  Skipping {name} (already in output)")
            continue
        try:
            kb["characters"][key] = research_character(client, name)
        except Exception as exc:
            print(f"  ERROR researching {name}: {exc}")
            kb["characters"][key] = {"character": name, "_error": str(exc)}
        _save(kb)

    # ── Weapons ──────────────────────────────────────────────────────────────
    for name in weapons_to_research:
        key = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        if key in kb["weapons"]:
            print(f"  Skipping weapon {name} (already done)")
            continue
        try:
            kb["weapons"][key] = research_weapon(client, name)
        except Exception as exc:
            print(f"  ERROR researching weapon {name}: {exc}")
            kb["weapons"][key] = {"weapon": name, "_error": str(exc)}
        _save(kb)

    # ── Scenes ───────────────────────────────────────────────────────────────
    for name in scenes_to_research:
        key = name[:40].lower().replace(" ", "_").replace("—", "").replace(",", "")
        if key in kb["scenes"]:
            print(f"  Skipping scene '{name[:40]}' (already done)")
            continue
        try:
            kb["scenes"][key] = research_scene(client, name)
        except Exception as exc:
            print(f"  ERROR researching scene '{name[:40]}': {exc}")
            kb["scenes"][key] = {"scene": name, "_error": str(exc)}
        _save(kb)

    print("\n" + "=" * 60)
    print("Research complete.")
    print(f"Output saved to: {OUTPUT_FILE}")
    print()
    print("NEXT STEPS:")
    print("  1. Open research_output/mythology_kb_raw.json")
    print("  2. Review each character entry against cultural references")
    print("  3. Edit/correct as needed")
    print("  4. Integrate verified content into lib/mythology_knowledge.py")
    print("  5. Only then run Phase B (grounded story generation)")
    print("=" * 60)


def _save(kb: dict):
    OUTPUT_DIR.mkdir(exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    tmp.replace(OUTPUT_FILE)


if __name__ == "__main__":
    main()
