"""
lib/tts.py — Expressive TTS for Telugu Katalu.

Primary  : Gemini 2.5 Flash TTS — context-aware, performance-style narration.
           The model understands "grandmother storytelling" style and naturally
           varies pace, pitch, and emphasis without rigid SSML rules.

Fallback : Google Cloud TTS Chirp3-HD — original implementation if Gemini TTS
           is unavailable or fails.

Audio pipeline (Gemini path):
  Gemini TTS → PCM bytes → MP3 file (lameenc, pure Python — no ffmpeg needed)

Requires for Gemini path:
  pip install lameenc
"""

import html
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_SAMPLE_RATE = 24000   # Hz — Gemini TTS PCM output rate


# ── Voice style map ───────────────────────────────────────────────────────────
# Maps the short voice name (after stripping "te-IN-Chirp3-HD-") to a
# performance description that Gemini uses to set its narration style.
_VOICE_STYLE: dict[str, str] = {
    "Autonoe":    "a loving, silver-haired Telugu grandmother telling bedtime stories by candlelight",
    "Gacrux":     "a wise village grandmother who has lived every joy and sorrow in her tales",
    "Callirrhoe": "a warm, emotionally expressive young aunt who makes children cry and laugh",
    "Leda":       "a gentle, melodic village narrator whose voice feels like a warm breeze",
    "Laomedeia":  "an animated, playful narrator who acts out every character with enthusiasm",
    "Iapetus":    "a slow, deliberate village elder who weighs every word like precious gold",
    "Enceladus":  "a deep, grave epic storyteller whose voice commands absolute silence",
    "Fenrir":     "a strong, measured narrator performing an epic tale around a campfire",
    "Charon":     "a classic, unhurried storyteller in the Panchatantra tradition",
    "Achird":     "an energetic, friendly young narrator who brings every adventure to life",
}
_DEFAULT_STYLE = "a warm Telugu storyteller performing for children aged 5-8"


def _extract_voice_short(voice_name: str) -> str:
    """te-IN-Chirp3-HD-Kore  →  Kore"""
    return voice_name.split("-")[-1]


def _build_performance_prompt(text: str, voice_name: str) -> str:
    """Wrap Telugu scene text in a narration-style instruction for Gemini TTS."""
    short = _extract_voice_short(voice_name)
    style = _VOICE_STYLE.get(short, _DEFAULT_STYLE)

    return (
        f"You are {style}. "
        f"Read the following Telugu story scene as a lively, engaging live performance for children aged 5-10.\n"
        f"Instructions:\n"
        f"- Keep a natural, upbeat pace throughout — children have short attention spans, keep the energy moving forward.\n"
        f"- Only slow down at the single most dramatic or emotional peak of the scene — nowhere else.\n"
        f"- Make emotions vivid and clear: joy sounds genuinely joyful, fear sounds truly afraid.\n"
        f"- When a character speaks (dialogue in quotes), give them a clearly distinct voice.\n"
        f"- This is a live performance. Keep children leaning in, not drifting away.\n\n"
        f"Story scene (Telugu):\n\n{text}"
    )


# ── PCM → MP3 conversion (pure Python, no ffmpeg) ────────────────────────────

def _pcm_to_mp3(pcm_data: bytes, output_path: Path) -> None:
    """Encode raw 16-bit mono PCM bytes to MP3 using lameenc (pure Python, no ffmpeg)."""
    try:
        import lameenc
    except ImportError:
        raise ImportError(
            "lameenc is required for Gemini TTS audio conversion.\n"
            "  pip install lameenc"
        )
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(_SAMPLE_RATE)
    encoder.set_channels(1)
    encoder.set_quality(2)   # 2 = highest quality
    mp3_data = encoder.encode(pcm_data) + encoder.flush()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(mp3_data)
    logger.debug(f"MP3 encode OK: {output_path.name} ({len(mp3_data) // 1024} KB)")


# ── Gemini TTS ────────────────────────────────────────────────────────────────

def _gemini_synthesize(text: str, voice_name: str, output_path: Path) -> bool:
    """Synthesize one scene with Gemini TTS. Returns True on success."""
    from google import genai
    from google.genai import types
    from lib.config import GEMINI_API_KEY

    short_voice = _extract_voice_short(voice_name)
    prompt = _build_performance_prompt(text, voice_name)

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=short_voice
                    )
                )
            ),
        ),
    )

    part = response.candidates[0].content.parts[0]
    raw = part.inline_data.data

    # SDK may return raw bytes or base64 string depending on version
    if isinstance(raw, str):
        import base64
        raw = base64.b64decode(raw)

    _pcm_to_mp3(raw, output_path)

    kb = output_path.stat().st_size / 1024
    logger.info(f"Gemini TTS OK: {output_path.name} ({kb:.1f} KB) voice={short_voice}")
    return True


# ── Cloud TTS fallback (original Chirp3-HD path) ─────────────────────────────

def _to_ssml(text: str) -> str:
    """Convert Telugu narration text to SSML for Cloud TTS.

    Chirp3-HD supports: <speak>, <break>, <p>, <s>
    Does NOT support: <prosody>, <emphasis>
    """
    segment_re = re.compile(r"(—|\.\.\.|\n\s*\n)")
    raw_segments = segment_re.split(text)

    ssml = ["<speak>"]
    for seg in raw_segments:
        if seg == "—":
            ssml.append('<break time="650ms"/>')
        elif seg == "...":
            ssml.append('<break time="900ms"/>')
        elif re.match(r"\n\s*\n", seg):
            ssml.append('<break time="800ms"/>')
        else:
            escaped = html.escape(seg.strip())
            if not escaped:
                continue
            escaped = re.sub(r"([!])([\s])", r'\1<break time="350ms"/>\2', escaped)
            escaped = re.sub(r"([?])([\s])", r'\1<break time="450ms"/>\2', escaped)
            escaped = re.sub(r"([.।])([\s])", r'\1<break time="500ms"/>\2', escaped)
            escaped = re.sub(r"([,])([\s])", r'\1<break time="150ms"/>\2', escaped)
            ssml.append(escaped)
    ssml.append("</speak>")
    result = "".join(ssml)
    logger.debug(f"SSML ({len(result)} chars): {result[:120]}...")
    return result


def _cloud_tts_synthesize(text: str, voice_name: str, output_path: Path) -> bool:
    """Fallback: Google Cloud TTS Chirp3-HD with SSML break tags."""
    from google.cloud import texttospeech

    ssml = _to_ssml(text)

    for attempt in range(1, 3):
        try:
            client = texttospeech.TextToSpeechClient()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="te-IN",
                    name=voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    sample_rate_hertz=22050,
                ),
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.audio_content)
            kb = len(response.audio_content) / 1024
            logger.info(f"Cloud TTS OK: {output_path.name} ({kb:.1f} KB) voice={voice_name}")
            return True

        except Exception as exc:
            logger.warning(f"Cloud TTS attempt {attempt}/2 failed ({voice_name}): {exc}")
            if attempt == 1:
                logger.info("Retrying in 2s...")
                time.sleep(2)

    raise RuntimeError(
        f"Cloud TTS failed for {output_path.name} after 2 attempts with {voice_name}. "
        f"Check ADC credentials and Chirp3-HD availability."
    )


# ── Public API ────────────────────────────────────────────────────────────────

def synthesize_scene(text: str, voice_name: str, output_path: Path) -> bool:
    """Synthesize one scene to MP3.

    Tries Gemini TTS first (expressive, context-aware narration).
    Falls back to Google Cloud TTS Chirp3-HD if Gemini TTS is unavailable or fails.

    Args:
        text:        Telugu narration text for the scene.
        voice_name:  Full Chirp3-HD voice name (e.g. "te-IN-Chirp3-HD-Autonoe").
                     Short name is derived automatically for Gemini TTS.
        output_path: Destination .mp3 path.
    Returns:
        True on success.
    Raises:
        RuntimeError if all paths fail.
    """
    _dep_missing = False

    # ── Attempt Gemini TTS (up to 2 tries) ───────────────────────────────────
    for attempt in range(1, 3):
        try:
            return _gemini_synthesize(text, voice_name, output_path)

        except ImportError as e:
            logger.warning(
                f"Gemini TTS skipped (missing dependency): {e}\n"
                f"  → Using Cloud TTS fallback. Install lameenc for better quality."
            )
            _dep_missing = True
            break

        except Exception as exc:
            logger.warning(f"Gemini TTS attempt {attempt}/2 failed: {exc}")
            if attempt == 1:
                time.sleep(3)

    if not _dep_missing:
        logger.info("Gemini TTS exhausted — falling back to Cloud TTS")

    # ── Cloud TTS fallback ────────────────────────────────────────────────────
    return _cloud_tts_synthesize(text, voice_name, output_path)
