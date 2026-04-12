from dotenv import load_dotenv
from groq import Groq
import edge_tts
import asyncio
import json, os, time, requests, random
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# ── CONFIG ──────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
STORIES_DIR      = "stories"
INDEX_FILE       = "stories/index.json"
TOPICS_FILE      = "topics.txt"
# ────────────────────────────────────────────────────

os.makedirs(STORIES_DIR, exist_ok=True)

# ── Pick topic avoiding duplicates ───────────────────
existing_titles = []
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        existing = json.load(f)
        existing_titles = [s["title"] for s in existing.get("stories", [])]

with open(TOPICS_FILE, "r", encoding="utf-8") as f:
    topics = [t.strip() for t in f.readlines() if t.strip()]

max_attempts = 10
STORY_TOPIC = None

for _ in range(max_attempts):
    candidate = random.choice(topics)
    already_exists = any(candidate in title or title in candidate
                        for title in existing_titles)
    if not already_exists:
        STORY_TOPIC = candidate
        break

if not STORY_TOPIC:
    print("⚠️ All topics used! Add more to topics.txt")
    STORY_TOPIC = random.choice(topics)

print(f"📖 Selected topic: {STORY_TOPIC}")
print(f"📚 Existing stories: {len(existing_titles)}")

# ── STEP 1: Generate Story ───────────────────────────
print("\n🔄 Generating Telugu story via Groq...")

groq_client = Groq(api_key=GROQ_API_KEY)

prompt = f"""You are a Telugu children's story writer and visual director.
Write a short moral story in Telugu about: {STORY_TOPIC}

Return ONLY valid JSON, no markdown, no backticks, nothing else:
{{
  "title": "story title in Telugu",
  "moral": "moral in Telugu",
  "main_character": "detailed physical description in English: age, clothing, hair, skin tone",
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

response = groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)

raw = response.choices[0].message.content.strip()
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()

story = json.loads(raw)
print(f"✅ Story: {story['title']}")
print(f"📖 Scenes: {len(story['scenes'])}")

# ── STEP 2: Create story folder ──────────────────────
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

with open(f"{story_dir}/story.json", "w", encoding="utf-8") as f:
    json.dump(story, f, ensure_ascii=False, indent=2)
print(f"✅ Story saved: {story_dir}/story.json")

# ── STEP 3: Generate Audio via Edge TTS ─────────────
print("\n🔄 Generating Telugu audio via Edge TTS...")

async def generate_audio(text, output_path):
    communicate = edge_tts.Communicate(text, voice="te-IN-ShrutiNeural")
    await communicate.save(output_path)

for scene in story["scenes"]:
    audio_file = f"{audio_dir}/scene{scene['id']}.mp3"
    asyncio.run(generate_audio(scene["text"], audio_file))
    print(f"✅ Audio: scene{scene['id']}.mp3")

# ── STEP 4: Generate Images via Leonardo ────────────
print("\n🔄 Generating images via Leonardo AI...")

headers = {
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
        headers=headers,
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
    print(f"  Waiting for generation...")
    time.sleep(15)

    result = requests.get(
        f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
        headers=headers,
        verify=False
    )

    images = result.json()["generations_by_pk"]["generated_images"]
    if not images:
        print(f"  ⚠️ No image returned")
        return

    img_data = requests.get(images[0]["url"], verify=False)
    with open(f"{image_dir}/scene{scene['id']}.jpg", "wb") as f:
        f.write(img_data.content)
    print(f"✅ Image saved: scene{scene['id']}.jpg");
    
    
for scene in story["scenes"]:
    generate_image(scene)
    time.sleep(3)

# ── STEP 5: Update index.json ────────────────────────
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
    "date":      story["date"]
})

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"✅ Index updated — total stories: {len(index['stories'])}")
print(f"\n🎉 Done! Open index.html to see your stories.")