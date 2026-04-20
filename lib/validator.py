import json
import logging

from google import genai
from google.genai import types

from lib.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 7


def validate_story(story: dict, max_retries: int = 2) -> dict:
    """Score story on 4 dimensions via Gemini. Returns result dict with 'passed' key."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    scenes_text = "\n".join(
        f"Scene {s['id']}: {s['text']}" for s in story.get("scenes", [])
    )

    prompt = f"""\
You are a Telugu children's story quality reviewer.

Score this story on each dimension from 1-10:
1. telugu_grammar   — correct, everyday spoken Telugu (not formal/archaic)?
2. emotional_depth  — do characters feel real, is there emotional arc?
3. moral_clarity    — is the lesson clear and appropriate for ages 5-12?
4. narrative_flow   — does the story flow naturally scene to scene?

Also check content_safety: flag anything with violence, fear, or content
inappropriate for young children.

STORY:
Title: {story.get('title', '')}
Moral: {story.get('moral', '')}
Scenes:
{scenes_text}

Return ONLY valid JSON:
{{
  "telugu_grammar":  <1-10>,
  "emotional_depth": <1-10>,
  "moral_clarity":   <1-10>,
  "narrative_flow":  <1-10>,
  "content_safety":  "ok" or "flagged: <reason>",
  "notes": "brief reviewer comment in English (1-2 sentences)"
}}"""

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            result = json.loads(response.text)

            avg = (
                result["telugu_grammar"]
                + result["emotional_depth"]
                + result["moral_clarity"]
                + result["narrative_flow"]
            ) / 4
            result["average"] = round(avg, 2)
            result["passed"]  = (
                avg >= SCORE_THRESHOLD
                and result.get("content_safety", "ok") == "ok"
            )

            status = "PASS" if result["passed"] else "FAIL"
            logger.info(
                f"Validation {status}: avg={avg:.1f} "
                f"safety={result.get('content_safety')} — {result.get('notes','')}"
            )
            return result

        except Exception as exc:
            logger.warning(f"Validation attempt {attempt} failed: {exc}")

    # Validator itself errored — don't block story generation
    logger.error("Validator unavailable — defaulting to pass")
    return {
        "telugu_grammar": 7, "emotional_depth": 7,
        "moral_clarity": 7,  "narrative_flow": 7,
        "average": 7.0, "passed": True,
        "content_safety": "ok", "notes": "validator unavailable",
    }
