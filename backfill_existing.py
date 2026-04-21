"""
backfill_existing.py — One-time schema_v2 migration for existing stories.

What it does:
  - Patches every story.json with: category, subcategory, topic, schema_version=2
  - Adds category field to every entry in stories/index.json
  - Adds retired=true to story 20260413_091514 (duplicate title, no media)
  - Skips index.json for incomplete stories (no audio/images)
  - Logs all decisions to logs/backfill_decisions.log

Run ONCE after approval. Safe to re-run (idempotent).
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR  = Path(__file__).parent
STORIES   = BASE_DIR / "stories"
INDEX     = STORIES / "index.json"
LOG_DIR   = BASE_DIR / "logs"
LOG_FILE  = LOG_DIR / "backfill_decisions.log"

LOG_DIR.mkdir(exist_ok=True)

# ── SUBCATEGORY MAP (approved mapping from planning session) ──────────────────
SUBCATEGORY_MAP = {
    "20260417_001550": ("neeti", "animal_morals",  "దయగల ఏనుగు"),
    "20260416_193055": ("neeti", "wisdom_tales",   "గర్వపడిన గులాబీ మరియు వినయమైన చెట్టు"),
    "20260416_080122": ("neeti", "human_values",   "నిజాయితీ అయిన కట్టెల కాడు"),
    "20260412_181108": ("neeti", "wisdom_tales",   "తెలివైన వ్యాపారి"),
    "20260412_173904": ("neeti", "animal_morals",  "మూర్ఖుడైన గాడిద"),
    "20260412_143220": ("neeti", "human_values",   "నమ్మకద్రోహి మిత్రుడు"),
    "20260412_135946": ("neeti", "animal_morals",  "అందమైన నెమలి గర్వం"),
    "20260412_131731": ("neeti", "human_values",   "ఐక్యతలో బలం"),
    "20260412_130708": ("neeti", "human_values",   "ఓర్పు గల రైతు"),
    "20260411_174344": ("neeti", "wisdom_tales",   "అత్యాశ యొక్క పరిణామాలు"),
    "20260411_171746": ("neeti", "human_values",   "స్నేహం యొక్క విలువ"),
    # Orphaned — incomplete (no audio/images): patch story.json only, skip index
    "20260413_091353": ("neeti", "wisdom_tales",   "అందమైన తోట మరియు సోమరి మాలి"),
    # Retired — duplicate title, no media: patch story.json + retired=true, skip index
    "20260413_091514": ("neeti", "human_values",   "నిజాయితీ అయిన కట్టెల కాడు"),
}

RETIRED_IDS    = {"20260413_091514"}
INCOMPLETE_IDS = {"20260413_091353"}  # has story.json but no audio/images


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_complete(story_id: str) -> bool:
    """Check story has at least one audio AND one image file."""
    story_dir = STORIES / story_id
    audio_files = list((story_dir / "audio").glob("scene*.mp3")) if (story_dir / "audio").exists() else []
    image_files = list((story_dir / "images").glob("scene*.jpg")) if (story_dir / "images").exists() else []
    return len(audio_files) > 0 and len(image_files) > 0


def patch_story_json(story_id: str, category: str, subcategory: str, topic: str, retire: bool = False):
    path = STORIES / story_id / "story.json"
    if not path.exists():
        log(f"SKIP  {story_id}: story.json not found")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = []

    if data.get("schema_version") != 2:
        data["schema_version"] = 2
        changed.append("schema_version=2")

    if data.get("category") != category:
        data["category"] = category
        changed.append(f"category={category}")

    if data.get("subcategory") != subcategory:
        data["subcategory"] = subcategory
        changed.append(f"subcategory={subcategory}")

    if data.get("topic") != topic:
        data["topic"] = topic
        changed.append(f"topic={topic}")

    if retire and not data.get("retired"):
        data["retired"] = True
        changed.append("retired=true")

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"PATCH {story_id}: {', '.join(changed)}")
    else:
        log(f"OK    {story_id}: already up to date")


def patch_index(story_id: str, category: str, subcategory: str, topic: str):
    with open(INDEX, "r", encoding="utf-8") as f:
        index = json.load(f)

    changed = False
    for entry in index.get("stories", []):
        if entry["id"] == story_id:
            if entry.get("category") != category:
                entry["category"] = category
                changed = True
            if entry.get("subcategory") != subcategory:
                entry["subcategory"] = subcategory
                changed = True
            if entry.get("topic") != topic:
                entry["topic"] = topic
                changed = True
            break
    else:
        log(f"WARN  {story_id}: not found in index.json — skipping index patch")
        return

    if changed:
        with open(INDEX, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        log(f"INDEX {story_id}: updated category/subcategory/topic")
    else:
        log(f"INDEX {story_id}: already up to date")


def main():
    log("=" * 60)
    log("backfill_existing.py START")
    log("=" * 60)

    for story_id, (category, subcategory, topic) in SUBCATEGORY_MAP.items():
        is_retired    = story_id in RETIRED_IDS
        is_incomplete = story_id in INCOMPLETE_IDS

        # Always patch story.json
        patch_story_json(story_id, category, subcategory, topic, retire=is_retired)

        if is_retired:
            log(f"RETIRE {story_id}: retired=true set, skipping index")
            continue

        if is_incomplete:
            log(f"INCOMPLETE {story_id}: no audio/images — skipping index")
            continue

        # Verify completeness before touching index (safety check)
        if not is_complete(story_id):
            log(f"INCOMPLETE {story_id}: audio or images missing at runtime — skipping index")
            continue

        patch_index(story_id, category, subcategory, topic)

    log("=" * 60)
    log("backfill_existing.py DONE")
    log("=" * 60)
    print(f"\nLog written to: {LOG_FILE}")


if __name__ == "__main__":
    main()
