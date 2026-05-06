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

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
GCP_PROJECT_ID  = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION    = os.getenv("GCP_LOCATION", "us-central1")
# Explicit opt-in required to allow AI Studio path when GCP_PROJECT_ID is absent.
# Set ALLOW_AI_STUDIO=true ONLY for local dev/testing without a GCP project.
# Never set this to true in a production environment with GCP_PROJECT_ID available.
ALLOW_AI_STUDIO = os.getenv("ALLOW_AI_STUDIO", "false").lower() == "true"

# ── Startup routing log — prints once at import time ──────────────────────────
if GCP_PROJECT_ID:
    print(
        f"[CONFIG] Routing: Vertex AI | project={GCP_PROJECT_ID} | location={GCP_LOCATION}"
        f" | ALLOW_AI_STUDIO={ALLOW_AI_STUDIO}",
        flush=True,
    )
elif ALLOW_AI_STUDIO:
    print("[CONFIG] Routing: AI Studio API key | ALLOW_AI_STUDIO=true", flush=True)
else:
    print(
        "[CONFIG] WARNING: GCP_PROJECT_ID not set and ALLOW_AI_STUDIO!=true — "
        "make_client() will raise RuntimeError on first call",
        flush=True,
    )


def make_client():
    """Return a Gemini client routed to Vertex AI when GCP_PROJECT_ID is set.

    Safety guard: if GCP_PROJECT_ID is absent and ALLOW_AI_STUDIO is not
    explicitly 'true', raises RuntimeError instead of silently billing AI Studio.

    The client is automatically wrapped in CostTrackedClient so every
    generate_content call is logged to logs/cost_audit.jsonl without any
    per-module changes.
    """
    from google import genai

    if GCP_PROJECT_ID:
        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    else:
        if not ALLOW_AI_STUDIO:
            raise RuntimeError(
                "[CONFIG] Refusing to create AI Studio client: GCP_PROJECT_ID is not set "
                "and ALLOW_AI_STUDIO is not 'true'.\n"
                "  Fix 1 (recommended): set GCP_PROJECT_ID in .env to route via Vertex AI\n"
                "  Fix 2 (dev/testing): set ALLOW_AI_STUDIO=true in .env to allow AI Studio explicitly"
            )
        client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        from lib.cost_tracker import CostTrackedClient
        return CostTrackedClient(client)
    except Exception:
        # If cost_tracker is unavailable for any reason, return the plain client.
        return client

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
