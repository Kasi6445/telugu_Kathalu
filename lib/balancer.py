import json
import logging
import random

from lib.config import make_client, save_categories

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

    sub_data    = categories[cat_key]["subcategories"][sub_key]
    used_topics = {s.get("topic") for s in index_stories if s.get("topic")}
    available   = [t for t in sub_data["topics"] if t not in used_topics]

    if not available:
        logger.info(f"All topics used in {cat_key}/{sub_key} — auto-expanding via Gemini")
        new_topics = _generate_new_topics(cat_key, sub_key, categories, index_stories)
        categories[cat_key]["subcategories"][sub_key]["topics"].extend(new_topics)
        save_categories(categories)
        # Filter new topics against already-used topics — Gemini may regenerate used concepts
        available = [t for t in new_topics if t not in used_topics]
        if not available:
            logger.warning("All generated new topics were already used — using them anyway as last resort")
            available = new_topics
        logger.info(f"Added {len(new_topics)} new topics to {cat_key}/{sub_key}, {len(available)} genuinely new")

    topic = random.choice(available)
    return cat_key, sub_key, topic


def _generate_new_topics(cat_key: str, sub_key: str, categories: dict, index_stories: list) -> list:
    from google.genai import types

    cat  = categories[cat_key]
    sub  = cat["subcategories"][sub_key]

    # Build concept fingerprints from ALL existing stories to avoid conceptual repetition
    # (not just topic string matching — Gemini must avoid the same moral/theme entirely)
    used_topics  = [s.get("topic",  "") for s in index_stories if s.get("topic")]
    used_morals  = [s.get("moral",  "") for s in index_stories if s.get("moral")]
    used_titles  = [s.get("title",  "") for s in index_stories if s.get("title")]
    used_chars   = [s.get("main_character", "") for s in index_stories if s.get("main_character")]

    # Also build subcategory-specific list for tighter focus
    sub_stories  = [s for s in index_stories
                    if s.get("category") == cat_key and s.get("subcategory") == sub_key]
    sub_concepts = "\n".join(
        f"  - Topic: {s.get('topic','')} | Moral: {s.get('moral','')[:100]}"
        for s in sub_stories
    )

    prompt = (
        f"You are a children's story curator for Telugu kids aged 5-10.\n"
        f"Generate 10 genuinely NEW and DISTINCT story topic ideas for this slot:\n\n"
        f"Category    : {cat['telugu_name']}\n"
        f"Subcategory : {sub['telugu_name']}\n"
        f"Tone        : {cat['tone']}\n\n"
        f"CRITICAL RULE — CONCEPT UNIQUENESS:\n"
        f"Every topic you generate must teach a DIFFERENT lesson and use DIFFERENT characters\n"
        f"from every story already published. It is not enough to change the wording — the\n"
        f"core theme, moral, and story concept must be genuinely different.\n\n"
        f"Already published concepts in this subcategory (do NOT repeat ANY of these themes):\n"
        f"{sub_concepts if sub_concepts else '  (none yet)'}\n\n"
        f"All published topic strings across the entire library (exact matches forbidden):\n"
        + "\n".join(f"  - {t}" for t in used_topics)
        + f"\n\nAll published morals/lessons (do NOT produce stories with the same lesson):\n"
        + "\n".join(f"  - {m[:120]}" for m in used_morals)
        + "\n\nReturn ONLY a JSON array of 10 unique topic strings in Telugu. No explanation.\n"
        f"Each topic must represent a completely new concept not covered above."
    )

    client = make_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.9,
        ),
    )
    return json.loads(response.text)
