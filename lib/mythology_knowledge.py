"""
lib/mythology_knowledge.py — Canonical visual descriptions for Hindu mythology characters.

These descriptions are injected into image prompts to prevent AI from generating
historically/iconographically wrong depictions (e.g., Lakshmana as an old monk).

Each description is image-prompt-ready: 2-3 sentences, visual only, no narrative.
Sources: Valmiki Ramayana (Gita Press), Srimad Bhagavatam, classical Telugu/South Indian
temple iconography, Tanjore painting tradition.
"""

# Canonical image-prompt descriptions keyed by lowercase English character name.
CHARACTER_ANCHORS: dict[str, str] = {
    "rama": (
        "Rama: a young prince with dark blue-black (shyama) complexion, tall and broad-shouldered, "
        "long arms reaching to his knees (Ajanabahu). "
        "During forest exile: wearing saffron-orange bark cloth (valkala), matted hair tied in a topknot (jata-mukuta), "
        "carrying his curved bow Kodanda and a quiver of arrows over his shoulder. "
        "Lotus-shaped eyes with a gentle reddish tinge at the corners. Noble, calm expression."
    ),
    "lakshmana": (
        "Lakshmana: a young prince (mid-twenties) with a warm golden-brown complexion, muscular and alert — "
        "slightly shorter and more compact than Rama. "
        "During forest exile: wearing saffron-orange bark cloth (valkala), matted hair tied in a topknot, "
        "carrying his bow and full quiver, always standing in a protective, watchful posture. "
        "He is NOT old, NOT a monk, NOT grey-haired — he is a vigorous young warrior-prince. "
        "Determined, loyal expression; the devoted younger brother."
    ),
    "sita": (
        "Sita: a graceful young woman (mid-twenties) with a fair golden complexion and long dark hair "
        "adorned with jasmine flowers. "
        "Wearing a silk saree in deep red or golden hues, with traditional gold ornaments: "
        "necklace, bangles, nose ring, and earrings. "
        "Eyes reflecting deep wisdom and quiet dignity. Serene, composed expression."
    ),
    "hanuman": (
        "Hanuman: a powerful vanara (divine monkey) with reddish-gold fur and an intelligent, noble face. "
        "Wearing an orange-red dhoti with a golden belt; broad chest, strong arms, a long tail "
        "curved upward behind him. "
        "Often depicted carrying a gada (mace) or with hands folded in anjali mudra (namaste). "
        "Devoted, fearless expression — NOT a comical monkey; a divine warrior and devotee."
    ),
    "ravana": (
        "Ravana: a powerful king-demon (rakshasa) with dark complexion and ten heads, each wearing a crown. "
        "Richly dressed in deep red and gold royal garments with elaborate gold ornaments and armlets. "
        "Carries multiple weapons including a sword and spear across his many arms. "
        "Commanding, imperious expression — fearsome but regal."
    ),
    "agni devudu": (
        "Agni Devudu (Fire God): a radiant deity with a golden-amber complexion suffused with an inner glow. "
        "Two or four arms; wearing flaming red-orange garments and a crown of fire. "
        "One hand holds a flaming torch (shakti); he is surrounded by sacred fire but appears benevolent, not frightening. "
        "He is NOT depicted as a human bystander — he clearly emerges from or stands within fire."
    ),
    "krishna": (
        "Krishna: a young cowherd or prince with a dark blue (shyama) complexion, wearing a yellow "
        "silk pitambara garment and a peacock feather (morpankh) in his crown. "
        "Carrying a flute (bansuri); adorned with a garland of forest flowers (vaijayanti mala) "
        "and tulsi beads. Playful, divine smile — the eternal beloved."
    ),
    "prahlada": (
        "Prahlada: a young boy (approximately 8-10 years old) with a serene complexion, "
        "wearing simple white or pale yellow garments. "
        "Hands often folded in prayer (anjali mudra). Calm, unwavering, devotional expression "
        "even in the midst of danger — he radiates inner peace."
    ),
    "narasimha": (
        "Narasimha: a fierce deity with a lion's head (golden mane, bared teeth) on a powerful human body. "
        "Multiple arms holding weapons including the Sudarshana Chakra. "
        "Wearing royal ornaments; body radiating divine energy. "
        "Expression: ferocious toward demons, protective toward devotees."
    ),
    "vali": (
        "Vali: a powerful vanara king with dark complexion, very large and muscular — "
        "visibly bigger and more imposing than Sugriva. "
        "Wearing a golden crown and royal vanara ornaments, carrying a heavy mace. "
        "Fierce, dominant expression."
    ),
    "sugriva": (
        "Sugriva: a vanara with reddish-gold complexion, slightly smaller and leaner than Vali. "
        "Wearing simple golden ornaments. Alert, determined expression."
    ),
    "bharata": (
        "Bharata: a young prince with a fair complexion, wearing a simple white dhoti "
        "and minimal ornaments (he lives in austerity while Rama is in exile). "
        "Gentle, grief-stricken yet dignified expression. Carries Rama's sandals (paduka) "
        "as a symbol of his brother's authority."
    ),
    "garuda": (
        "Garuda: a mighty eagle-deity (vahana of Vishnu) with golden feathers, a human torso, "
        "and enormous wings. Wears a crown and divine ornaments. "
        "Majestic, powerful, swift appearance."
    ),
}

# Name aliases — common variations map to canonical keys
_ALIASES: dict[str, str] = {
    "lakshman": "lakshmana",
    "laxman": "lakshmana",
    "laxmana": "lakshmana",
    "ramachandra": "rama",
    "ramachandrudu": "rama",
    "lord rama": "rama",
    "lord krishna": "krishna",
    "agni": "agni devudu",
    "agnidevudu": "agni devudu",
    "fire god": "agni devudu",
    "fire deity": "agni devudu",
    "lord hanuman": "hanuman",
    "anjaneya": "hanuman",
}


def get_character_anchor(name: str) -> str | None:
    """Return canonical image-prompt description for a mythology character, or None."""
    key = name.lower().strip()
    key = _ALIASES.get(key, key)
    return CHARACTER_ANCHORS.get(key)


def get_canonical_prompt_block() -> str:
    """Return a formatted block of all canonical descriptions for injection into Pass 1 prompt."""
    lines = [
        "CANONICAL CHARACTER DESCRIPTIONS — use these VERBATIM for known characters:",
        "(These are the authoritative visual anchors used in image generation.)",
        "",
    ]
    for char_name, desc in CHARACTER_ANCHORS.items():
        lines.append(f"  {char_name.title()}: {desc}")
        lines.append("")
    return "\n".join(lines)
