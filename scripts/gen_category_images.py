#!/usr/bin/env python3
"""
Generate HD square (512x512) category card images for mobile view.
Saves to assets/categories/mobile/<key>.webp
"""
import sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent.parent
OUT_DIR    = BASE_DIR / "assets" / "categories" / "mobile"
OUT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(BASE_DIR))

CATEGORIES = {
    "neeti": {
        "file": "niti-kathalu.webp",
        "prompt": (
            "A beautifully illuminated ancient Sanskrit manuscript book, open, glowing with warm golden light, "
            "intricate lotus and vine border decorations, soft amber candlelight, rich jewel tones, "
            "cinematic digital illustration, dark rich background, no text, square composition."
        ),
    },
    "podupu": {
        "file": "podupu-kathalu.webp",
        "prompt": (
            "A large ornate traditional Indian brass pot overflowing with golden coins and a glowing question mark "
            "carved in the metal, mystical twinkling lights floating around it, deep teal and gold color palette, "
            "cinematic illustration, dark moody background, no text, square composition."
        ),
    },
    "tenali": {
        "file": "tenaali-raama.webp",
        "prompt": (
            "Portrait of Tenaali Ramakrishna, a witty Indian court jester in traditional Vijayanagara-era royal "
            "attire — vibrant silk clothes, peacock feather turban, mischievous smile and bright intelligent eyes, "
            "warm golden court lighting, ornate palace pillars in background, cinematic illustration, no text, "
            "square composition."
        ),
    },
    "panchatantra": {
        "file": "panchatantran.webp",
        "prompt": (
            "A majestic lion sitting proudly in a lush ancient Indian forest, surrounded by a clever crow, "
            "a wise turtle, and a deer — animals gathered as friends, dappled golden forest light, rich greens "
            "and ambers, Panchatantra folk-art style, cinematic illustration, no text, square composition."
        ),
    },
    "ramayana": {
        "file": "raamaayanan.webp",
        "prompt": (
            "Lord Rama standing heroically, holding his divine golden bow aimed at the sky, wearing royal blue "
            "and gold attire, peacock feather crown, sacred forest background with glowing lotus flowers, "
            "epic Hindu mythology cinematic illustration style, rich purple and gold tones, no text, "
            "square composition."
        ),
    },
    "samethalu": {
        "file": "saametalu.webp",
        "prompt": (
            "A traditional Indian oil lamp (diya) glowing with a warm flame, surrounded by colorful rangoli "
            "patterns, ancient Telugu script motifs etched in copper, golden and amber light, deep dark "
            "background, rich cultural warmth, cinematic illustration, no text, square composition."
        ),
    },
    "janapada": {
        "file": "jaanapadan.webp",
        "prompt": (
            "A mystical Telugu village at night — thatched huts with glowing lanterns, an ancient banyan tree "
            "under a full moon with stars, a storyteller silhouette sitting by a fire, deep indigo and warm "
            "amber tones, folk art cinematic illustration style, no text, square composition."
        ),
    },
    "bhagavatam": {
        "file": "bhaagavatan.webp",
        "prompt": (
            "Lord Krishna as a young divine child, holding a golden flute, wearing peacock feather crown and "
            "yellow silk, surrounded by golden lotus flowers and a divine celestial glow, deep blue and gold "
            "color palette, sacred Hindu devotional art cinematic illustration, no text, square composition."
        ),
    },
}

def generate_image(key, info):
    from lib.config import make_client
    from google.genai import types

    client = make_client()

    style_suffix = (
        " Style: painterly cinematic illustration, rich saturated colors, dramatic lighting, "
        "soft depth of field, 8K resolution quality, no watermarks, no borders, no UI elements, "
        "portrait-friendly square crop."
    )
    prompt = info["prompt"] + style_suffix

    out_png  = OUT_DIR / f"{key}.png"
    out_webp = OUT_DIR / info["file"]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[types.Part(text=prompt)],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    out_png.write_bytes(part.inline_data.data)
                    print(f"  [{key}] PNG saved ({len(part.inline_data.data)//1024} KB)")
                    return True
            print(f"  [{key}] No image in response, attempt {attempt+1}")
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = [15, 30, 60][attempt]
                print(f"  [{key}] Rate limited — waiting {wait}s")
                time.sleep(wait)
            else:
                print(f"  [{key}] Error: {e}")
                return False
    return False


def compress(key, info):
    from PIL import Image as PIL
    out_png  = OUT_DIR / f"{key}.png"
    out_webp = OUT_DIR / info["file"]
    if not out_png.exists():
        return False
    img = PIL.open(out_png).convert("RGB")
    # Resize to 512x512 square (cover-crop from center)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img  = img.crop((left, top, left + side, top + side))
    img  = img.resize((512, 512), PIL.LANCZOS)
    img.save(out_webp, "WEBP", quality=88, method=6)
    size_kb = out_webp.stat().st_size // 1024
    out_png.unlink()
    print(f"  [{key}] -> {info['file']} ({size_kb} KB)")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Comma-separated category keys to regenerate (e.g. neeti,tenali)")
    args = parser.parse_args()

    keys = list(CATEGORIES.keys())
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip() in CATEGORIES]

    print(f"Generating {len(keys)} category images -> {OUT_DIR}\n")
    ok = 0
    for key in keys:
        print(f"Generating: {key}")
        if generate_image(key, CATEGORIES[key]):
            if compress(key, CATEGORIES[key]):
                ok += 1
        time.sleep(3)  # avoid burst rate-limiting between images

    print(f"\nDone: {ok}/{len(keys)} images generated.")
