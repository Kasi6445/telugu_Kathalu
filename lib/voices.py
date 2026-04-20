"""
lib/voices.py — Approved voice catalog and smart picker for Telugu Katalu.

10 auditioned Chirp3-HD voices only. All others are rejected.
Tweak classifications at runtime with update_voice_metadata() — no code edit needed.
"""

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# Persists user-driven metadata tweaks without touching source code
_OVERRIDE_FILE = Path(__file__).parent.parent / "voice_metadata_overrides.json"

# ── Approved voice catalog ─────────────────────────────────────────────────────
VOICE_CATALOG: dict[str, dict] = {
    "te-IN-Chirp3-HD-Achird": {
        "gender": "male",
        "age_feel": "young_adult",
        "warmth": "medium",
        "energy": "medium",
        "best_for": ["adventure", "witty", "friendly_narrator"],
    },
    "te-IN-Chirp3-HD-Autonoe": {
        "gender": "female",
        "age_feel": "mature",
        "warmth": "high",
        "energy": "medium",
        "best_for": ["grandmother_tales", "moral_stories", "gentle_narration"],
    },
    "te-IN-Chirp3-HD-Callirrhoe": {
        "gender": "female",
        "age_feel": "young_adult",
        "warmth": "high",
        "energy": "medium_high",
        "best_for": ["emotional_tales", "romance", "sister_narrator"],
    },
    "te-IN-Chirp3-HD-Charon": {
        "gender": "male",
        "age_feel": "mature",
        "warmth": "medium",
        "energy": "medium",
        "best_for": ["classic_fables", "panchatantra", "measured_storyteller"],
    },
    "te-IN-Chirp3-HD-Enceladus": {
        "gender": "male",
        "age_feel": "mature",
        "warmth": "medium_low",
        "energy": "medium",
        "best_for": ["mythology", "epic_tales", "grave_narrator"],
    },
    "te-IN-Chirp3-HD-Fenrir": {
        "gender": "male",
        "age_feel": "mature",
        "warmth": "medium",
        "energy": "medium_high",
        "best_for": ["adventure", "ramayana", "strong_male_narrator"],
    },
    "te-IN-Chirp3-HD-Laomedeia": {
        "gender": "female",
        "age_feel": "young_adult",
        "warmth": "high",
        "energy": "high",
        "best_for": ["children_tales", "playful", "animated_narration"],
    },
    "te-IN-Chirp3-HD-Gacrux": {
        "gender": "female",
        "age_feel": "mature",
        "warmth": "high",
        "energy": "medium",
        "best_for": ["grandmother_tales", "folk_stories", "janapada"],
    },
    "te-IN-Chirp3-HD-Iapetus": {
        "gender": "male",
        "age_feel": "mature",
        "warmth": "medium_low",
        "energy": "medium_low",
        "best_for": ["wisdom_tales", "birbal_tenali", "wise_elder"],
    },
    "te-IN-Chirp3-HD-Leda": {
        "gender": "female",
        "age_feel": "young_adult",
        "warmth": "high",
        "energy": "medium",
        "best_for": ["village_tales", "warm_narrator", "samethalu"],
    },
}

# ── Subcategory voice pools ────────────────────────────────────────────────────
# Slugs match categories.json exactly.
# User's brief used Panchatantra tantra names (mitra_bheda etc.) and Ramayana kanda names —
# mapped here to the actual slugs: friendship_betrayal, animal_wisdom, clever_tricks,
# devotion_tales, courage_tales, dharma_tales.
SUBCATEGORY_VOICE_POOL: dict[tuple, list] = {
    # Neeti — warm feminine narration dominant
    ("neeti", "animal_morals"):  ["te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Leda",    "te-IN-Chirp3-HD-Achird"],
    ("neeti", "human_values"):   ["te-IN-Chirp3-HD-Autonoe",   "te-IN-Chirp3-HD-Gacrux",   "te-IN-Chirp3-HD-Callirrhoe"],
    ("neeti", "wisdom_tales"):   ["te-IN-Chirp3-HD-Iapetus",   "te-IN-Chirp3-HD-Charon",   "te-IN-Chirp3-HD-Autonoe"],

    # Panchatantra — measured male dominant
    ("panchatantra", "friendship_betrayal"): ["te-IN-Chirp3-HD-Charon",  "te-IN-Chirp3-HD-Iapetus", "te-IN-Chirp3-HD-Achird"],
    ("panchatantra", "animal_wisdom"):       ["te-IN-Chirp3-HD-Charon",  "te-IN-Chirp3-HD-Achird",  "te-IN-Chirp3-HD-Leda"],
    ("panchatantra", "clever_tricks"):       ["te-IN-Chirp3-HD-Charon",  "te-IN-Chirp3-HD-Fenrir",  "te-IN-Chirp3-HD-Iapetus"],

    # Ramayana — epic mature male dominant
    ("ramayana", "dharma_tales"):   ["te-IN-Chirp3-HD-Fenrir",    "te-IN-Chirp3-HD-Enceladus", "te-IN-Chirp3-HD-Charon"],
    ("ramayana", "devotion_tales"): ["te-IN-Chirp3-HD-Enceladus", "te-IN-Chirp3-HD-Fenrir",    "te-IN-Chirp3-HD-Autonoe"],
    ("ramayana", "courage_tales"):  ["te-IN-Chirp3-HD-Fenrir",    "te-IN-Chirp3-HD-Enceladus", "te-IN-Chirp3-HD-Callirrhoe"],

    # Tenali — witty, court-smart
    ("tenali", "court_wit"):        ["te-IN-Chirp3-HD-Achird",  "te-IN-Chirp3-HD-Iapetus",   "te-IN-Chirp3-HD-Charon"],
    ("tenali", "clever_schemes"):   ["te-IN-Chirp3-HD-Leda",    "te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Gacrux"],
    ("tenali", "funny_adventures"): ["te-IN-Chirp3-HD-Iapetus", "te-IN-Chirp3-HD-Enceladus", "te-IN-Chirp3-HD-Achird"],

    # Birbal — similar to Tenali
    ("birbal", "royal_dilemmas"):   ["te-IN-Chirp3-HD-Iapetus",   "te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Charon"],
    ("birbal", "wisdom_tests"):     ["te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Iapetus"],
    ("birbal", "witty_comebacks"):  ["te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Leda"],

    # Janapada — warm village voices
    ("janapada", "village_tales"):  ["te-IN-Chirp3-HD-Gacrux",    "te-IN-Chirp3-HD-Leda",      "te-IN-Chirp3-HD-Autonoe"],
    ("janapada", "hero_tales"):     ["te-IN-Chirp3-HD-Gacrux",    "te-IN-Chirp3-HD-Fenrir",    "te-IN-Chirp3-HD-Leda"],
    ("janapada", "magical_tales"):  ["te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Gacrux",    "te-IN-Chirp3-HD-Callirrhoe"],

    # Podupu — playful, riddle energy
    ("podupu", "nature_riddles"):   ["te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Leda",   "te-IN-Chirp3-HD-Achird"],
    ("podupu", "royal_riddles"):    ["te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Laomedeia", "te-IN-Chirp3-HD-Leda"],
    ("podupu", "clever_escapes"):   ["te-IN-Chirp3-HD-Iapetus",   "te-IN-Chirp3-HD-Achird",    "te-IN-Chirp3-HD-Charon"],

    # Samethalu — sage narration
    ("samethalu", "life_wisdom"):   ["te-IN-Chirp3-HD-Iapetus", "te-IN-Chirp3-HD-Autonoe", "te-IN-Chirp3-HD-Charon"],
    ("samethalu", "hard_lessons"):  ["te-IN-Chirp3-HD-Charon",  "te-IN-Chirp3-HD-Gacrux",  "te-IN-Chirp3-HD-Iapetus"],
    ("samethalu", "relationships"): ["te-IN-Chirp3-HD-Autonoe", "te-IN-Chirp3-HD-Gacrux",  "te-IN-Chirp3-HD-Leda"],
}

_DEFAULT_POOL = ["te-IN-Chirp3-HD-Autonoe", "te-IN-Chirp3-HD-Charon", "te-IN-Chirp3-HD-Achird"]

_MALE_KEYWORDS = [
    "king", "prince", "man", "boy", "father", "son", "brother",
    "grandfather", "old man", "merchant", "warrior", "hunter",
    "lion", "bull", "donkey", "monkey", "crow", "crane", "fox",
    " he ", " his ", "రాజు", "కుర్రాడు", "వ్యాపారి",
]
_FEMALE_KEYWORDS = [
    "queen", "princess", "woman", "girl", "mother", "daughter",
    "sister", "grandmother", "old woman", "fairy", "deer", "hen",
    " she ", " her ", "రాణి", "అమ్మాయి", "అమ్మ",
]


def _load_overrides() -> dict:
    if _OVERRIDE_FILE.exists():
        try:
            return json.loads(_OVERRIDE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _effective_catalog() -> dict:
    """Merge base catalog with any user overrides."""
    catalog = {k: dict(v) for k, v in VOICE_CATALOG.items()}
    for voice, overrides in _load_overrides().items():
        if voice in catalog:
            catalog[voice].update(overrides)
    return catalog


def _category_pool(category: str) -> list:
    """Union of all voices across a category's subcategories (fallback)."""
    seen: list = []
    for (cat, _sub), voices in SUBCATEGORY_VOICE_POOL.items():
        if cat == category:
            for v in voices:
                if v not in seen:
                    seen.append(v)
    return seen


def pick_voice(category: str, subcategory: str, story_metadata: dict,
               recent_stories: list | None = None) -> str:
    """Pick the best voice from the 10-voice catalog for this story.

    Selection order:
    1. Subcategory default pool → category pool → _DEFAULT_POOL
    2. Narrow by main_character gender (if strongly gendered)
    3. Narrow by tone (playful → high-energy; wise → low-energy)
    4. Remove voices used in last 2 stories of same subcategory (variety)
    5. random.choice() from remaining candidates
    """
    catalog    = _effective_catalog()
    candidates = list(
        SUBCATEGORY_VOICE_POOL.get((category, subcategory))
        or _category_pool(category)
        or _DEFAULT_POOL
    )

    # 1. Gender bias from main_character description
    desc         = (story_metadata.get("main_character") or "").lower()
    male_score   = sum(1 for kw in _MALE_KEYWORDS   if kw in desc)
    female_score = sum(1 for kw in _FEMALE_KEYWORDS if kw in desc)

    if male_score > female_score + 1:
        narrowed = [v for v in candidates if catalog.get(v, {}).get("gender") == "male"]
        if narrowed:
            candidates = narrowed
    elif female_score > male_score + 1:
        narrowed = [v for v in candidates if catalog.get(v, {}).get("gender") == "female"]
        if narrowed:
            candidates = narrowed

    # 2. Tone bias
    tone = (story_metadata.get("tone") or "").lower()
    if any(t in tone for t in ["playful", "children", "animated", "fun", "humor"]):
        narrowed = [v for v in candidates if catalog.get(v, {}).get("energy") in ("high", "medium_high")]
        if narrowed:
            candidates = narrowed
    elif any(t in tone for t in ["wise", "reflective", "grave", "sage", "moral", "epic"]):
        narrowed = [v for v in candidates if catalog.get(v, {}).get("energy") in ("medium_low", "low")]
        if narrowed:
            candidates = narrowed

    # 3. Variety — avoid last 2 voices used in same subcategory
    if recent_stories:
        recent_voices = [
            s.get("voice") for s in recent_stories
            if s.get("category") == category and s.get("subcategory") == subcategory
        ][:2]
        narrowed = [v for v in candidates if v not in recent_voices]
        if narrowed:
            candidates = narrowed

    chosen = random.choice(candidates)
    logger.info(
        f"Voice picked: {chosen.replace('te-IN-Chirp3-HD-', '')} "
        f"(pool={category}/{subcategory}, "
        f"gender_bias={'M' if male_score > female_score+1 else 'F' if female_score > male_score+1 else '-'}, "
        f"candidates={len(candidates)})"
    )
    return chosen


def update_voice_metadata(voice_name: str, updates: dict):
    """Persist metadata tweaks without editing source code.

    Example:
        update_voice_metadata("te-IN-Chirp3-HD-Laomedeia", {"energy": "medium"})
    """
    if voice_name not in VOICE_CATALOG:
        raise ValueError(f"Unknown voice (not in approved catalog): {voice_name}")
    overrides = _load_overrides()
    overrides.setdefault(voice_name, {}).update(updates)
    _OVERRIDE_FILE.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Voice metadata override saved: {voice_name} → {updates}")
