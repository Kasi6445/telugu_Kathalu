import json
import logging
import random

from lib.config import GEMINI_API_KEY, save_categories

logger = logging.getLogger(__name__)


def pick_next_slot(categories: dict, index_stories: list) -> tuple[str, str, str]:
    """Return (cat_key, sub_key, topic) for the next story slot.

    Uses subcategory-aware least-count balancing with random tiebreak so no
    single category dominates when multiple slots share the minimum count.
    """
    counts: dict[tuple, int] = {}
    for cat_key, cat_data in categories.items():
        for sub_key in cat_data["subcategories"]:
            counts[(cat_key, sub_key)] = 0

    for story in index_stories:
        key = (story.get("category"), story.get("subcategory"))
        if key in counts:
            counts[key] += 1

    min_count = min(counts.values())
    candidates = [k for k, v in counts.items() if v == min_count]
    cat_key, sub_key = random.choice(candidates)

    sub_data   = categories[cat_key]["subcategories"][sub_key]
    used_topics = {s.get("topic") for s in index_stories if s.get("topic")}
    available   = [t for t in sub_data["topics"] if t not in used_topics]

    if not available:
        logger.info(f"All topics used in {cat_key}/{sub_key} — auto-expanding via Gemini")
        new_topics = _generate_new_topics(cat_key, sub_key, categories, index_stories)
        categories[cat_key]["subcategories"][sub_key]["topics"].extend(new_topics)
        save_categories(categories)
        available = new_topics
        logger.info(f"Added {len(new_topics)} new topics to {cat_key}/{sub_key}")

    topic = random.choice(available)
    return cat_key, sub_key, topic


def _generate_new_topics(cat_key: str, sub_key: str, categories: dict, index_stories: list) -> list:
    from google import genai
    from google.genai import types

    cat  = categories[cat_key]
    sub  = cat["subcategories"][sub_key]
    used = [s.get("topic") for s in index_stories if s.get("topic")]

    prompt = (
        f"Generate 8 new story topic titles in Telugu for:\n"
        f"Category: {cat['telugu_name']}\n"
        f"Subcategory: {sub['telugu_name']}\n"
        f"Tone: {cat['tone']}\n\n"
        f"Already used topics (do NOT repeat):\n"
        + "\n".join(f"- {t}" for t in used)
        + "\n\nReturn ONLY a JSON array of 8 topic strings in Telugu. No explanation."
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.8,
        ),
    )
    return json.loads(response.text)
