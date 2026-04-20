import logging
import time
from pathlib import Path

from google import genai
from google.genai import types

from lib.config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_API_KEY, STYLE_LOCK

logger = logging.getLogger(__name__)

_DIRECTOR_PREFIX = (
    "Children's picture book illustration for ages 5-10. "
    "Gentle, warm, peaceful tone — NO violence, NO aggressive poses, NO scary imagery. "
)

_IMAGE_MODELS = [
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-3.0-generate-002",
]

QUOTA_SLEEP     = 15   # seconds between image requests (1 req/min quota)
_RETRY_429_WAIT = 70   # seconds to wait after a 429 before one retry

_STYLE_MARKER = "Hand-painted children's storybook illustration"


def _validate_and_repair(prompt: str, main_character: str, setting: str,
                          repairs_log: Path) -> str:
    repaired = prompt
    repairs  = []

    if main_character not in repaired:
        repaired += f" {main_character}"
        repairs.append("character_lock")

    if setting not in repaired:
        repaired += f" {setting}"
        repairs.append("world_lock")

    if _STYLE_MARKER not in repaired:
        repaired += f" {STYLE_LOCK}"
        repairs.append("style_lock")

    if repairs:
        msg = (
            f"REPAIR — added: {', '.join(repairs)}\n"
            f"  original[:120]: {prompt[:120]}\n\n"
        )
        with open(repairs_log, "a", encoding="utf-8") as f:
            f.write(msg)
        logger.warning(f"Prompt repaired: {repairs}")

    return repaired


def _vertex_client() -> genai.Client:
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)


def _gen_config() -> types.GenerateImagesConfig:
    return types.GenerateImagesConfig(
        number_of_images=1,
        aspect_ratio="4:3",
        safety_filter_level="BLOCK_ONLY_HIGH",
        person_generation="ALLOW_ADULT",
    )


def _save_image(response, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response.generated_images[0].image.save(str(output_path))


def _soften_prompt(prompt: str) -> str:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Rewrite this image prompt to be gentler and more child-friendly. "
                "Keep all key visual details but remove anything that could be flagged "
                "as aggressive or unsafe:\n\n" + prompt
            ),
            config=types.GenerateContentConfig(temperature=0.3),
        )
        return resp.text.strip()
    except Exception:
        return prompt


def _log_failure(output_path: Path, prompt: str, logs_dir: Path):
    log_file = logs_dir / "image_failures.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"FAILED: {output_path}\nPROMPT: {prompt[:300]}\n\n")
    logger.error(f"All image models failed for {output_path.name} — logged")


def generate_image(image_prompt: str, main_character: str, setting: str,
                   output_path: Path, logs_dir: Path) -> bool:
    repairs_log  = logs_dir / "prompt_repairs.log"
    clean_prompt = _validate_and_repair(image_prompt, main_character, setting, repairs_log)
    full_prompt  = _DIRECTOR_PREFIX + clean_prompt

    client = _vertex_client()
    cfg    = _gen_config()

    for model in _IMAGE_MODELS:
        try:
            logger.info(f"Image: trying {model} → {output_path.name}")
            resp = client.models.generate_images(model=model, prompt=full_prompt, config=cfg)
            _save_image(resp, output_path)
            logger.info(f"Image saved: {output_path.name} via {model}")
            return True

        except Exception as exc:
            err = str(exc)

            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                logger.warning(f"429 on {model} — waiting {_RETRY_429_WAIT}s then retry once")
                time.sleep(_RETRY_429_WAIT)
                try:
                    resp = client.models.generate_images(model=model, prompt=full_prompt, config=cfg)
                    _save_image(resp, output_path)
                    logger.info(f"Image saved after 429 retry: {output_path.name}")
                    return True
                except Exception as exc2:
                    logger.warning(f"{model} retry failed: {exc2}")

            elif "safety" in err.lower() or "block" in err.lower():
                logger.warning(f"Safety block on {model} — retrying with softened prompt")
                soft = _soften_prompt(full_prompt)
                try:
                    resp = client.models.generate_images(model=model, prompt=soft, config=cfg)
                    _save_image(resp, output_path)
                    logger.info(f"Image saved with softened prompt: {output_path.name}")
                    return True
                except Exception as exc3:
                    logger.warning(f"Softened prompt failed on {model}: {exc3}")

            else:
                logger.warning(f"{model} failed: {exc}")

    _log_failure(output_path, full_prompt, logs_dir)
    return False
