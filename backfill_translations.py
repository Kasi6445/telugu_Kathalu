#!/usr/bin/env python3
"""Backfill title_te_en, title_en, moral_te_en, moral_en, text_te_en, text_en
into every story.json that doesn't yet have them.

Usage:
    python backfill_translations.py          # process ONE story, show diff, stop
    python backfill_translations.py --all    # process all remaining stories
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

from lib.config import GEMINI_API_KEY, LOGS_DIR, STORIES_DIR
from lib.story_gen import telugu_to_readable_english

FLASH_MODEL = "gemini-2.5-flash"

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

log_file = LOGS_DIR / "backfill_translations.log"
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(fh)


# ── Core helpers ──────────────────────────────────────────────────────────────

def needs_backfill(story: dict) -> bool:
    return not (story.get("title_te_en") and story.get("title_en"))


def add_transliterations(story: dict) -> dict:
    story["title_te_en"] = telugu_to_readable_english(story["title"])
    story["moral_te_en"] = telugu_to_readable_english(story["moral"])
    for scene in story["scenes"]:
        scene["text_te_en"] = telugu_to_readable_english(scene["text"])
    return story


def add_english_translations(story: dict) -> dict:
    payload = {
        "title": story["title"],
        "moral": story["moral"],
        "scenes": [{"id": s["id"], "text": s["text"]} for s in story["scenes"]],
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
    response = client.models.generate_content(
        model=FLASH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    translations = json.loads(response.text)
    story["title_en"] = translations["title_en"]
    story["moral_en"] = translations["moral_en"]

    scene_map = {s["id"]: s for s in story["scenes"]}
    for t_scene in translations.get("scenes", []):
        if t_scene["id"] in scene_map:
            scene_map[t_scene["id"]]["text_en"] = t_scene["text_en"]

    return story


def show_diff(original: dict, updated: dict):
    bar = "=" * 64
    print(f"\n{bar}")
    print("DIFF — new fields added to story.json")
    print(bar)
    print(f"title:       {original['title']}")
    print(f"title_te_en: {updated['title_te_en']}")
    print(f"title_en:    {updated['title_en']}")
    print()
    print(f"moral:       {original['moral'][:90]}")
    print(f"moral_te_en: {updated['moral_te_en'][:90]}")
    print(f"moral_en:    {updated['moral_en'][:90]}")
    print()
    for scene in updated["scenes"]:
        sid = scene["id"]
        orig_text = next(s["text"] for s in original["scenes"] if s["id"] == sid)
        print(f"Scene {sid}:")
        print(f"  te:    {orig_text[:80]}{'...' if len(orig_text) > 80 else ''}")
        te_en = scene.get("text_te_en", "")
        en    = scene.get("text_en", "")
        print(f"  te-en: {te_en[:80]}{'...' if len(te_en) > 80 else ''}")
        print(f"  en:    {en[:80]}{'...' if len(en) > 80 else ''}")
        print()
    print(bar)


def process_story(path: Path) -> tuple[bool, dict | None, dict | None]:
    """Process one story. Returns (modified, original, updated)."""
    story = json.loads(path.read_text(encoding="utf-8"))

    if not needs_backfill(story):
        logger.info(f"SKIP (already done): {path.parent.name}")
        return False, None, None

    logger.info(f"Processing: {path.parent.name} — \"{story['title']}\"")
    original = json.loads(json.dumps(story))  # deep copy for diff

    story = add_transliterations(story)
    story = add_english_translations(story)

    # Write back atomically
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

    logger.info(f"DONE: {path.parent.name} — \"{story['title_en']}\"")
    return True, original, story


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Process all remaining stories")
    args = parser.parse_args()

    all_paths = sorted(STORIES_DIR.glob("*/story.json"))
    pending = [
        p for p in all_paths
        if needs_backfill(json.loads(p.read_text(encoding="utf-8")))
    ]

    print(f"Stories found: {len(all_paths)} total, {len(pending)} need backfill")

    if not pending:
        print("All stories already backfilled.")
        return

    if not args.all:
        # Single-story preview run
        path = pending[0]
        print(f"\nProcessing ONE story for preview: {path.parent.name}")
        modified, original, updated = process_story(path)
        if modified:
            show_diff(original, updated)
            remaining = len(pending) - 1
            print(f"\nDone. {remaining} stories still need backfill.")
            print('Run with --all to process the remaining stories.')
        return

    # Full backfill
    done = 0
    failed = []
    for path in pending:
        try:
            modified, _, _ = process_story(path)
            if modified:
                done += 1
                time.sleep(1)  # avoid Flash rate limits
        except Exception as exc:
            logger.error(f"FAILED: {path.parent.name} — {exc}")
            failed.append(path.parent.name)

    print(f"\nBackfill complete: {done} updated, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
