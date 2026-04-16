from dotenv import load_dotenv
from groq import Groq
import json, os, time, requests, random, base64
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# ── CONFIG ───────────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")    # Get free at aistudio.google.com
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
SARVAM_API_KEY   = os.getenv("SARVAM_API_KEY")

STORIES_DIR = "stories"
INDEX_FILE  = "stories/index.json"
TOPICS_FILE = "topics.txt"

# ── CHOOSE STORY AI ──────────────────────────────────────────────────────────
# "gemini" → Free, 1500 req/day, better creative writing (recommended)
# "groq"   → Free, 14400 req/day, fast
STORY_AI = "groq"

# ── SARVAM VOICES — Random pick each time! ───────────────────────────────────
FEMALE_VOICES = ["ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya"]
MALE_VOICES   = ["rahul", "rohan", "amit", "dev", "ratan", "varun", "manan", "kabir"]
ALL_VOICES    = FEMALE_VOICES + MALE_VOICES

# Pick randomly from all voices each run
SARVAM_VOICE = random.choice(ALL_VOICES)
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(STORIES_DIR, exist_ok=True)

# ── Pick topic avoiding duplicates ───────────────────────────────────────────
existing_titles = []
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        existing = json.load(f)
        existing_titles = [s["title"] for s in existing.get("stories", [])]

with open(TOPICS_FILE, "r", encoding="utf-8") as f:
    topics = [t.strip() for t in f.readlines() if t.strip()]

STORY_TOPIC = None
for _ in range(10):
    candidate = random.choice(topics)
    already_exists = any(candidate in title or title in candidate
                         for title in existing_titles)
    if not already_exists:
        STORY_TOPIC = candidate
        break

if not STORY_TOPIC:
    print("⚠️ All topics used! Add more to topics.txt")
    STORY_TOPIC = random.choice(topics)

print(f"📖 Topic           : {STORY_TOPIC}")
print(f"📚 Existing stories: {len(existing_titles)}")
print(f"🤖 Story AI        : {STORY_AI.upper()}")
print(f"🎙️  Sarvam voice   : {SARVAM_VOICE} (randomly picked)")

# ── STORY PROMPT ─────────────────────────────────────────────────────────────
STORY_PROMPT = f"""You are a Telugu children's story writer and visual director.
Write a short moral story in Telugu about: {STORY_TOPIC}

Return ONLY valid JSON, no markdown, no backticks, nothing else:
{{
  "title": "story title in Telugu",
  "moral": "moral in Telugu",
  "main_character": "detailed physical description in English of the PRIMARY character. Translate the character name correctly from Telugu. Age, appearance, clothing details.",
  "setting": "specific environment in English with time of day and lighting",
  "scenes": [
    {{
      "id": 1,
      "text": "scene in Telugu (2-3 sentences)",
      "image_prompt": "Cinematic action scene in English: describe exactly what character is DOING, emotion, body language, environment details, lighting"
    }}
  ]
}}

Rules:
- Generate between 4 to 8 scenes depending on story flow
- Story text in Telugu script only
- image_prompt must describe ACTION not just presence
- image_prompt in English only
- Return only JSON
"""

# ── STEP 1: Generate Story ────────────────────────────────────────────────────
print("\n🔄 Generating Telugu story...")

raw = ""

if STORY_AI == "gemini":
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not in .env — falling back to Groq")
        STORY_AI = "groq"
    else:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": STORY_PROMPT}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 4096
                }
            }
        )
        if response.status_code != 200:
            print(f"❌ Gemini error: {response.text}")
            print("⚠️ Falling back to Groq...")
            STORY_AI = "groq"
        else:
            raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print("✅ Story generated via Google Gemini 1.5 Flash")

if STORY_AI == "groq":
    groq_client = Groq(api_key=GROQ_API_KEY)
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": STORY_PROMPT}],
        temperature=0.7
    )
    raw = response.choices[0].message.content.strip()
    print("✅ Story generated via Groq Llama")

# Clean JSON if wrapped in backticks
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()

story = json.loads(raw)
print(f"✅ Title : {story['title']}")
print(f"📖 Scenes: {len(story['scenes'])}")

# ── STEP 2: Create story folder ───────────────────────────────────────────────
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
story_dir = f"{STORIES_DIR}/{timestamp}"
audio_dir = f"{story_dir}/audio"
image_dir = f"{story_dir}/images"

os.makedirs(story_dir, exist_ok=True)
os.makedirs(audio_dir, exist_ok=True)
os.makedirs(image_dir, exist_ok=True)

story["id"]        = timestamp
story["date"]      = datetime.now().strftime("%Y-%m-%d")
story["thumbnail"] = f"stories/{timestamp}/images/scene1.jpg"
story["voice"]     = SARVAM_VOICE   # save which voice was used

with open(f"{story_dir}/story.json", "w", encoding="utf-8") as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"✅ Story saved: {story_dir}/story.json")

# ── STEP 3: Generate Audio via Sarvam TTS ────────────────────────────────────
print(f"\n🔄 Generating audio via Sarvam — voice: {SARVAM_VOICE}...")

def generate_audio_sarvam(text, speaker, output_path):
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [text],
        "target_language_code": "te-IN",
        "speaker": speaker,
        "model": "bulbul:v3",
        "pace": 1.0,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "audio_format": "mp3"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"  ❌ Sarvam error: {response.text}")
        return False

    data = response.json()
    audio_base64 = data.get("audios", [None])[0]
    if not audio_base64:
        print(f"  ❌ No audio returned")
        return False

    audio_bytes = base64.b64decode(audio_base64)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    size_kb = len(audio_bytes) / 1024
    print(f"  ✅ {os.path.basename(output_path)} ({size_kb:.1f} KB)")
    return True

for scene in story["scenes"]:
    audio_file = f"{audio_dir}/scene{scene['id']}.mp3"
    generate_audio_sarvam(scene["text"], SARVAM_VOICE, audio_file)

# ── STEP 4: Generate Images via Leonardo ──────────────────────────────────────
print("\n🔄 Generating images via Leonardo AI...")

leo_headers = {
    "Authorization": f"Bearer {LEONARDO_API_KEY}",
    "Content-Type": "application/json"
}

def generate_image(scene):
    image_prompt = (
        f"{scene['image_prompt']}, "
        f"character: {story['main_character']}, "
        f"children's book illustration, Indian art style, warm colors, no text, no watermark"
    )
    print(f"  Scene {scene['id']}: {image_prompt[:80]}...")

    r = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/generations",
        headers=leo_headers,
        json={
            "prompt": image_prompt,
            "modelId": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
            "width": 768,
            "height": 512,
            "num_images": 1,
            "alchemy": True
        },
        verify=False
    )

    if r.status_code != 200:
        print(f"  ⚠️ Failed: {r.text}")
        return

    generation_id = r.json()["sdGenerationJob"]["generationId"]
    print(f"  ⏳ Waiting for image...")
    time.sleep(15)

    result = requests.get(
        f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
        headers=leo_headers,
        verify=False
    )

    images = result.json()["generations_by_pk"]["generated_images"]
    if not images:
        print(f"  ⚠️ No image returned")
        return

    img_data = requests.get(images[0]["url"], verify=False)
    with open(f"{image_dir}/scene{scene['id']}.jpg", "wb") as f:
        f.write(img_data.content)
    print(f"  ✅ scene{scene['id']}.jpg saved")

for scene in story["scenes"]:
    generate_image(scene)
    time.sleep(3)

# ── STEP 5: Update index.json ──────────────────────────────────────────────────
print("\n🔄 Updating story index...")

if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)
else:
    index = {"stories": []}

index["stories"].insert(0, {
    "id":        story["id"],
    "title":     story["title"],
    "moral":     story["moral"],
    "thumbnail": story["thumbnail"],
    "date":      story["date"],
    "voice":     SARVAM_VOICE
})

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"✅ Index updated — total stories: {len(index['stories'])}")

# ── STEP 6: Update sitemap.xml ────────────────────────────────────────────────
print("\n🔄 Updating sitemap.xml...")

def generate_sitemap():
    base_url     = "https://telugu-kathalu.pages.dev"
    BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
    stories_path = os.path.join(BASE_DIR, "stories")
    urls = []

    urls.append(f"""  <url>
    <loc>{base_url}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""")

    for folder in sorted(os.listdir(stories_path)):
        folder_path = os.path.join(stories_path, folder)
        if os.path.isdir(folder_path):
            urls.append(f"""  <url>
    <loc>{base_url}/stories/{folder}/</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"✅ sitemap.xml updated with {len(urls)} URLs")

generate_sitemap()

print(f"\n🎉 Done! Story '{story['title']}' generated!")
print(f"🎙️  Voice used: {SARVAM_VOICE}")
print(f"📁 Location  : {story_dir}")
print(f"\n💡 Run: git add . && git commit -m 'Add: {story['title']}' && git push")