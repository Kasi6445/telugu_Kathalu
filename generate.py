from dotenv import load_dotenv
from groq import Groq
import json, os, time, requests, random, base64
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# ── CONFIG ───────────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
SARVAM_API_KEY   = os.getenv("SARVAM_API_KEY")

STORIES_DIR = "stories"
INDEX_FILE  = "stories/index.json"
TOPICS_FILE = "topics.txt"

# ── SARVAM VOICES ─────────────────────────────────────────────────────────────
FEMALE_VOICES = ["ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya"]
MALE_VOICES   = ["rahul", "rohan", "amit", "dev", "ratan", "varun", "manan", "kabir"]
ALL_VOICES    = FEMALE_VOICES + MALE_VOICES
SARVAM_VOICE  = random.choice(ALL_VOICES)

# ── CATEGORIES ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "neeti": {
        "name": "నీతి కథలు",
        "emoji": "📚",
        "topics": [
            "అహంకారి సింహం మరియు చిన్న ఎలుక",
            "నిజాయితీ అయిన కట్టెల కాడు",
            "తెలివైన కాకి మరియు నీళ్ల కుండ",
            "అందమైన నెమలి గర్వం",
            "కష్టపడే చీమ మరియు సోమరి మిడత",
            "స్వార్థపరుడైన కుక్క",
            "అబద్ధాలు చెప్పే కుర్రాడు",
            "ఐక్యతలో బలం",
            "దయగల ఏనుగు",
            "తెలివైన కుందేలు మరియు సింహం",
            "మూర్ఖుడైన గాడిద",
            "నమ్మకద్రోహి మిత్రుడు",
            "అందమైన తోట మరియు సోమరి మాలి",
            "గర్వపడిన గులాబీ మరియు వినయమైన చెట్టు",
            "తెలివైన వ్యాపారి",
            "ఓర్పు గల రైతు",
            "స్నేహం యొక్క విలువ",
            "అత్యాశ యొక్క పరిణామాలు",
        ]
    },
    "podupu": {
        "name": "పొడుపు కథలు",
        "emoji": "🧩",
        "topics": [
            "రాజు మరియు తెలివైన బాలుడు పొడుపు కథ",
            "అడవిలో పొడుపు కథ చెప్పిన నక్క",
            "మూడు పొడుపు కథలు మరియు బహుమతి",
            "తెలివైన పొడుపు కథతో రాజును మెప్పించిన బాలిక",
            "పొడుపు కథతో చెరసాల నుండి తప్పించుకున్న వ్యాపారి",
            "గురువు చెప్పిన పొడుపు కథ",
            "నది దాటడానికి పొడుపు కథ",
            "రాత్రి పొడుపు కథ చెప్పిన నక్షత్రాలు",
        ]
    },
    "tenali": {
        "name": "తెనాలి రామకృష్ణుడు",
        "emoji": "🎭",
        "topics": [
            "తెనాలి రామకృష్ణుడు మరియు పిల్లి పాలు",
            "తెనాలి రాముడు మరియు అహంకారి పండితుడు",
            "తెనాలి రాముడు మరియు బంగారు ఆంబలి",
            "తెనాలి రాముడు మరియు గుర్రం",
            "తెనాలి రాముడు మరియు రాజు పరీక్ష",
            "తెనాలి రాముడు మరియు దొంగ",
            "తెనాలి రాముడు మరియు వ్యాపారి తెలివి",
            "తెనాలి రాముడు మరియు మూర్ఖుల సభ",
            "తెనాలి రాముడు రాజుకు పాఠం నేర్పిన కథ",
            "తెనాలి రాముడు మరియు మాయగాడు",
        ]
    },
    "panchatantra": {
        "name": "పంచతంత్రం",
        "emoji": "🐒",
        "topics": [
            "పంచతంత్రం - సింహం మరియు ఎలుక",
            "పంచతంత్రం - నక్క మరియు ద్రాక్షపండ్లు",
            "పంచతంత్రం - కాకి మరియు నక్క",
            "పంచతంత్రం - తాబేలు మరియు హంసలు",
            "పంచతంత్రం - నాలుగు స్నేహితులు",
            "పంచతంత్రం - బ్రాహ్మణుడు మరియు పులి",
            "పంచతంత్రం - మూడు చేపలు",
            "పంచతంత్రం - సింహం మరియు కుందేలు",
            "పంచతంత్రం - పావురాలు మరియు వేటగాడు",
            "పంచతంత్రం - గాడిద మరియు సింహం చర్మం",
        ]
    },
    "ramayana": {
        "name": "రామాయణ రహస్యాలు",
        "emoji": "🏹",
        "topics": [
            "రాముడు మరియు శబరి భక్తి",
            "హనుమంతుడు లంక దహనం",
            "సీత స్వయంవరం",
            "రాముడు మరియు జటాయువు",
            "సుగ్రీవుడు మరియు వాలి యుద్ధం",
            "విభీషణుడు రాముని శరణు",
            "రాముడు వనవాసం",
            "లక్ష్మణ రేఖ రహస్యం",
        ]
    },
    "samethalu": {
        "name": "సామెతలు",
        "emoji": "💬",
        "topics": [
            "చేతులు కాలిన తరువాత ఆకులు పట్టుకున్న కథ",
            "అన్నం పెట్టిన చేయి కొట్టరాదు అనే సామెత కథ",
            "కాకికి తన పిల్లలు బంగారు పిల్లలు అనే కథ",
            "ఉప్పు తిన్న ఇంటికి రెండు పూటలు వెళ్ళాలి అనే కథ",
            "చదివిన విద్య చేతిలో ఉంటుంది అనే కథ",
            "ఓర్పు ఉన్న చోట భగవంతుడు ఉంటాడు అనే కథ",
            "కష్టేఫలే అనే సామెత కథ",
            "ఒకటి నేర్చుకుంటే పదింటికి పనికొస్తుంది అనే కథ",
        ]
    },
    "janapada": {
        "name": "జానపద కథలు",
        "emoji": "🪘",
        "topics": [
            "తెలుగు జానపద కథ - మాయా రాజకుమారి",
            "తెలుగు జానపద కథ - మంత్రగత్తె మరియు రైతు",
            "తెలుగు జానపద కథ - బంగారు పక్షి",
            "తెలుగు జానపద కథ - అడవి రాజు",
            "తెలుగు జానపద కథ - మాయా మర్రి చెట్టు",
            "తెలుగు జానపద కథ - వీర బాలుడు",
            "తెలుగు జానపద కథ - గాజుల అమ్మాయి",
            "తెలుగు జానపద కథ - చేపల రాజు",
        ]
    },
    "birbal": {
        "name": "అక్బర్ బీర్బల్",
        "emoji": "👑",
        "topics": [
            "బీర్బల్ తెలివి - నిజమైన తల్లి",
            "బీర్బల్ తెలివి - అత్యంత విలువైన వస్తువు",
            "బీర్బల్ తెలివి - ముగ్గురు మూర్ఖులు",
            "బీర్బల్ తెలివి - చాలా మంది మూర్ఖులు",
            "బీర్బల్ తెలివి - మండే కొవ్వొత్తి",
            "బీర్బల్ తెలివి - దేవుడు ఎక్కడ ఉన్నాడు",
            "బీర్బల్ తెలివి - నల్లని గోడ",
            "బీర్బల్ తెలివి - రాజు కలలో జవాబు",
        ]
    }
}

# ── PICK CATEGORY AND TOPIC ───────────────────────────────────────────────────
os.makedirs(STORIES_DIR, exist_ok=True)

existing_titles = []
existing_categories = {}
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        existing = json.load(f)
        for s in existing.get("stories", []):
            existing_titles.append(s["title"])
            cat = s.get("category", "neeti")
            existing_categories[cat] = existing_categories.get(cat, 0) + 1

# Pick category with fewest stories first for balance
sorted_cats = sorted(CATEGORIES.keys(), key=lambda c: existing_categories.get(c, 0))
SELECTED_CATEGORY = sorted_cats[0]

# Pick unused topic from that category
category_topics = CATEGORIES[SELECTED_CATEGORY]["topics"]
STORY_TOPIC = None

random.shuffle(category_topics)
for topic in category_topics:
    already_exists = any(topic in t or t in topic for t in existing_titles)
    if not already_exists:
        STORY_TOPIC = topic
        break

if not STORY_TOPIC:
    STORY_TOPIC = random.choice(category_topics)
    print(f"⚠️ All topics in {SELECTED_CATEGORY} used!")

cat_info = CATEGORIES[SELECTED_CATEGORY]
print(f"📖 Topic    : {STORY_TOPIC}")
print(f"📂 Category : {cat_info['emoji']} {cat_info['name']}")
print(f"📚 Existing : {len(existing_titles)} stories")
print(f"🎙️ Voice    : {SARVAM_VOICE}")

# ── STORY PROMPT ──────────────────────────────────────────────────────────────
STORY_PROMPT = f"""You are an expert Telugu story writer specializing in {cat_info['name']}.

Write an engaging, emotionally rich Telugu story about: {STORY_TOPIC}

Category style guide:
- నీతి కథలు: Simple moral lesson, relatable characters, clear message
- పొడుపు కథలు: Include a clever riddle, build suspense, satisfying answer
- తెనాలి రామకృష్ణుడు: Witty humor, clever wordplay, Tenali outsmarts everyone
- పంచతంత్రం: Animal characters, wisdom teaching, ancient style
- రామాయణ రహస్యాలు: Devotion, bravery, dharma values
- సామెతలు: Build story around a Telugu proverb, teach its meaning
- జానపద కథలు: Magical elements, village setting, folklore tone
- అక్బర్ బీర్బల్: Emperor Akbar's court, Birbal's clever wit

Return ONLY valid JSON, no markdown, no backticks:
{{
  "title": "story title in Telugu",
  "moral": "moral or lesson in Telugu (one sentence)",
  "main_character": "detailed physical description in English of the PRIMARY character. Correctly translate Telugu name to English. Age, appearance, clothing.",
  "setting": "specific environment in English with time of day and lighting",
  "scenes": [
    {{
      "id": 1,
      "text": "scene in Telugu (2-3 engaging sentences with emotion)",
      "image_prompt": "Cinematic scene in English: exactly what character is DOING, facial expression, body language, environment, lighting mood"
    }}
  ]
}}

Rules:
- 5 to 8 scenes depending on story complexity
- All story text in Telugu script only
- image_prompt in English only describing ACTION
- main_character must correctly translate Telugu character name
- Make the story emotionally engaging and culturally authentic
- Return only JSON
"""

# ── STEP 1: Generate Story via Groq ──────────────────────────────────────────
print("\n🔄 Generating story via Groq...")

groq_client = Groq(api_key=GROQ_API_KEY)
response = groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": STORY_PROMPT}],
    temperature=0.8
)

raw = response.choices[0].message.content.strip()
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
story["category"]  = SELECTED_CATEGORY
story["thumbnail"] = f"stories/{timestamp}/images/scene1.jpg"
story["voice"]     = SARVAM_VOICE

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
        "pace": 0.9,
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
    print(f"  ✅ scene{os.path.basename(output_path)} ({size_kb:.1f} KB)")
    return True

for scene in story["scenes"]:
    audio_file = f"{audio_dir}/scene{scene['id']}.mp3"
    generate_audio_sarvam(scene["text"], SARVAM_VOICE, audio_file)

# ── STEP 4: Generate Images via Leonardo ─────────────────────────────────────
print("\n🔄 Generating images via Leonardo AI...")

leo_headers = {
    "Authorization": f"Bearer {LEONARDO_API_KEY}",
    "Content-Type": "application/json"
}

def generate_image(scene):
    image_prompt = (
        f"{scene['image_prompt']}, "
        f"character: {story['main_character']}, "
        f"Indian illustration style, warm rich colors, "
        f"children's storybook art, detailed background, no text, no watermark"
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
    print(f"  ⏳ Waiting...")
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

# ── STEP 5: Update index.json ─────────────────────────────────────────────────
print("\n🔄 Updating index.json...")

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
    "category":  SELECTED_CATEGORY,
    "voice":     SARVAM_VOICE
})

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
print(f"✅ Index updated — total: {len(index['stories'])} stories")

# ── STEP 6: Update sitemap.xml ────────────────────────────────────────────────
print("\n🔄 Updating sitemap.xml...")

base_url     = "https://telugukathalu.in"
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
stories_path = os.path.join(BASE_DIR, "stories")
urls = [f"""  <url>
    <loc>{base_url}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""]

for folder in sorted(os.listdir(stories_path)):
    folder_path = os.path.join(stories_path, folder)
    if os.path.isdir(folder_path):
        urls.append(f"""  <url>
    <loc>{base_url}/story.html?id={folder}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")

sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(sitemap)
print(f"✅ sitemap.xml updated — {len(urls)} URLs")

# ── DONE ──────────────────────────────────────────────────────────────────────
print(f"\n🎉 Done!")
print(f"📖 Story    : {story['title']}")
print(f"📂 Category : {cat_info['emoji']} {cat_info['name']}")
print(f"🎙️ Voice    : {SARVAM_VOICE}")
print(f"📁 Location : {story_dir}")
print(f"\n💡 Next: git add . && git commit -m 'Add: {story['title']}' && git push")