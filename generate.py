#!/usr/bin/env python3
"""
Telugu Katalu — Story Generation Pipeline

Usage:
  python generate.py            # generate one story → drafts/{timestamp}/
  python generate.py --dry-run  # print selected slot only, no API calls
"""
import argparse
import json
import logging
import sys

from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")

from lib.config import load_categories, load_index, DRAFTS_DIR, LOGS_DIR
from lib.balancer import pick_next_slot
from lib.story_gen import generate_story
from lib.tts import synthesize_scene
from lib.image_gen import generate_images_for_story
from lib.validator import validate_story

LOGS_DIR.mkdir(exist_ok=True)
DRAFTS_DIR.mkdir(exist_ok=True)

_log_file = LOGS_DIR / f"generation_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("generate")


def main():
    parser = argparse.ArgumentParser(description="Generate one Telugu story")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print selected slot without calling any APIs")
    args = parser.parse_args()

    categories = load_categories()
    index      = load_index()
    stories    = index.get("stories", [])

    cat_key, sub_key, topic = pick_next_slot(categories, stories)
    cat = categories[cat_key]
    sub = cat["subcategories"][sub_key]

    print(f"\n📂 Category   : {cat['emoji']} {cat['telugu_name']}")
    print(f"📁 Subcategory : {sub['telugu_name']}")
    print(f"📖 Topic       : {topic}")
    print(f"🎙️  Voice       : (assigned during generation)")

    if args.dry_run:
        print("\n✅ Dry-run complete — no API calls made.")
        return

    # ── Story generation with validation loop ────────────────────────────────
    story  = None
    scores = None

    for attempt in range(1, 4):
        logger.info(f"Generation attempt {attempt}/3")
        candidate = generate_story(cat_key, sub_key, topic, categories, stories)
        scores    = validate_story(candidate)

        if scores["passed"]:
            story = candidate
            break
        logger.warning(
            f"Rejected (avg={scores['average']}, safety={scores['content_safety']}) "
            f"— retrying ({attempt}/3)"
        )

    if story is None:
        logger.error("All 3 attempts failed validation — aborting")
        sys.exit(1)

    # ── Create draft folder ───────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_dir = DRAFTS_DIR / timestamp
    audio_dir = draft_dir / "audio"
    image_dir = draft_dir / "images"
    audio_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)

    story.update({
        "id":             timestamp,
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "category":       cat_key,
        "subcategory":    sub_key,
        "topic":          topic,
        "voice":          story.get("voice", ""),
        "thumbnail":      f"stories/{timestamp}/images/scene1.png",
        "schema_version": 2,
    })

    # ── Audio ─────────────────────────────────────────────────────────────────
    logger.info("Generating audio...")
    for scene in story["scenes"]:
        synthesize_scene(scene["text"], story["voice"], audio_dir / f"scene{scene['id']}.mp3")

    # ── Images ────────────────────────────────────────────────────────────────
    logger.info("Generating images...")
    generate_images_for_story(story, draft_dir, LOGS_DIR)

    # ── Save story.json ───────────────────────────────────────────────────────
    (draft_dir / "story.json").write_text(
        json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n🎉 Draft saved  : drafts/{timestamp}/")
    print(f"📖 Title        : {story['title']}")
    print(f"📊 Quality score: {scores['average']}/10")
    print(f"\n   Preview : python preview_draft.py {timestamp}")
    print(f"   Promote : python promote.py {timestamp}")
    print(f"   Reject  : python reject.py {timestamp}")


if __name__ == "__main__":
    main()
