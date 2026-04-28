import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = Path(__file__).parent.parent
STORIES_DIR = BASE_DIR / "stories"
INDEX_FILE  = STORIES_DIR / "index.json"
DRAFTS_DIR  = BASE_DIR / "drafts"
LOGS_DIR    = BASE_DIR / "logs"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION   = os.getenv("GCP_LOCATION", "us-central1")

BASE_URL = "https://www.telugukathalu.in"

STYLE_LOCK = (
    "Hand-painted children's storybook illustration, classic Indian Chandamama and Amar Chitra Katha style. "
    "DETAIL LEVEL: highly detailed backgrounds — trees with individual leaves, rocks with texture, "
    "flowing water with ripples, ground with soil grain. Visible pencil linework under soft watercolor washes. "
    "Rich environmental storytelling — every background element is carefully rendered, not flat or sparse. "
    "Expressive character faces with clear emotions. Warm earth-tone palette (terracotta, cream, sage green, warm ochre). "
    "Clean composition with breathing space. "
    "NOT photorealistic. NOT 3D render. NOT anime. NOT flat modern cartoon. NOT simple clip art. NOT dark or gritty. "
    "NO cracked earth, NO apocalyptic atmosphere, NO aggressive poses, "
    "NO spread wings unless scene is explicitly about flying, NO menacing expressions. "
    "Characters should look gentle, friendly, and age-appropriate for children 5-10."
)


def load_categories() -> dict:
    path = BASE_DIR / "categories.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_categories(categories: dict):
    path = BASE_DIR / "categories.json"
    tmp  = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_index() -> dict:
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"stories": []}
