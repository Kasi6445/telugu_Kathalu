"""
lib/tts.py — Expressive TTS for Telugu Katalu.

Each scene is synthesised in its own Gemini TTS call with a strong voice-anchor
prompt so the narrator sounds consistent across all scenes.

If a scene's audio file already exists in audio_dir, it is reused (cache hit,
$0.00). This makes re-runs of the pipeline free for already-generated scenes.

Fallback: If Gemini TTS fails, falls back to Google Cloud TTS Chirp3-HD.

Audio pipeline (Gemini path):
  Gemini TTS → PCM bytes → MP3 (lameenc, no ffmpeg)
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


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_scene_prompt(text: str, voice_name: str,
                        scene_num: int = 1, total_scenes: int = 1,
                        scene_context: str = "") -> str:
    """Per-scene prompt with voice anchor, emotional context, and natural pacing guidance."""
    short = _extract_voice_short(voice_name)
    style = _VOICE_STYLE.get(short, _DEFAULT_STYLE)

    # Emotional tone — affects warmth/energy ONLY, never overall pace
    context_line = ""
    if scene_context:
        context_line = (
            f"SCENE MOOD: {scene_context}\n"
            f"Adjust your TONE and WARMTH for this mood — do NOT change your overall pace:\n"
            f"  • Tense / sad → voice becomes quieter, more tender; keep forward momentum\n"
            f"  • Joyful / triumphant → brighter energy, more lift and warmth in the voice\n"
            f"  • Wonder / suspense → softer and more intimate; lean gently into key words\n"
            f"  • Battle / urgent → controlled forward energy — steady, clear, never rushed\n"
            f"  • Devotional / reverent → soft, flowing, sacred — smooth and connected\n\n"
        )

    return (
        f"You are {style}. Record this as a warm, natural Telugu audiobook scene "
        f"({scene_num} of {total_scenes}) for children aged 5–8.\n\n"

        f"{context_line}"

        f"SPEAK LIKE A REAL PERSON — this is the most critical instruction:\n"
        f"Speak the way a real grandmother actually talks to a child sitting in front of her — "
        f"connected, phrase-by-phrase, with natural rhythm and warmth throughout. "
        f"Your speech must flow continuously and conversationally. "
        f"Do NOT speak word-by-word. Do NOT insert long silences or gaps between sentences. "
        f"Keep the energy alive and forward-moving at all times.\n\n"

        f"PACE: Natural and lively — like genuine storytelling conversation. "
        f"Not fast, not slow, not flat. A grandmother who loves this story "
        f"speaks with real feeling and keeps the child leaning in. "
        f"Flat or dragging delivery will lose the child's attention immediately.\n\n"

        f"PAUSES — brief and natural only:\n"
        f"- Em-dash (—): one quick dramatic breath, then continue immediately\n"
        f"- Three dots (...): one short beat of suspense — do not linger, then move on\n"
        f"- Sentence end (। or .): one natural breath — short — then continue with energy\n"
        f"- Comma (,): the lightest possible pause; keep the rhythm flowing\n"
        f"- Quoted dialogue (\".....\"): slightly warmer voice for the character; "
        f"return to narrator pace immediately after the closing quote\n\n"

        f"VOICE CONSISTENCY: Your pitch, character, and warmth are FIXED and identical "
        f"across all {total_scenes} scenes in this story.\n\n"

        f"Telugu story text:\n\n{text}"
    )


# ── PCM → MP3 conversion (pure Python, no ffmpeg) ────────────────────────────

def _pcm_to_mp3(pcm_data: bytes, output_path: Path) -> None:
    """Encode raw 16-bit mono PCM bytes to MP3 using lameenc."""
    try:
        import lameenc
    except ImportError:
        raise ImportError(
            "lameenc is required for Gemini TTS.\n"
            "  pip install lameenc"
        )
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(_SAMPLE_RATE)
    encoder.set_channels(1)
    encoder.set_quality(2)
    mp3_data = encoder.encode(pcm_data) + encoder.flush()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(mp3_data)
    logger.debug(f"MP3 encode OK: {output_path.name} ({len(mp3_data) // 1024} KB)")


# ── Gemini TTS — single-scene call ───────────────────────────────────────────

def _gemini_raw_pcm(prompt: str, voice_name: str) -> bytes:
    """Make one Gemini TTS call and return raw PCM bytes."""
    from google.genai import types
    from lib.config import make_client

    short_voice = _extract_voice_short(voice_name)
    client      = make_client()

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

    candidates = response.candidates
    if (not candidates
            or not candidates[0].content
            or not candidates[0].content.parts):
        raise RuntimeError("Gemini TTS returned no audio candidates")
    part = candidates[0].content.parts[0]
    inline = part.inline_data
    if inline is None or inline.data is None:
        raise RuntimeError("Gemini TTS returned no inline audio data")
    raw: bytes | str = inline.data

    if isinstance(raw, str):
        import base64
        raw = base64.b64decode(raw)

    return raw


# ── Public API ────────────────────────────────────────────────────────────────

def synthesize_story(scenes: list[dict], voice_name: str, audio_dir: Path) -> None:
    """
    Synthesise each scene individually and save as per-scene MP3 files.
    Scenes whose audio file already exists in audio_dir are skipped (cache hit).

    Args:
        scenes:     story["scenes"] list — each dict must have "id" and "text".
        voice_name: Full Chirp3-HD voice name (e.g. "te-IN-Chirp3-HD-Fenrir").
        audio_dir:  Directory to write scene1.mp3, scene2.mp3, …
    """
    n = len(scenes)
    audio_dir.mkdir(parents=True, exist_ok=True)

    for idx, scene in enumerate(scenes, start=1):
        out = audio_dir / f"scene{scene['id']}.mp3"
        if out.exists():
            print(f"  [TTS CACHE] scene {scene['id']} reused — $0.00", flush=True)
            continue
        _synthesize_scene_file(
            scene["text"], voice_name, out, idx, n,
            scene_context=scene.get("scene_visual", ""),
        )


def synthesize_scene(text: str, voice_name: str, output_path: Path,
                     scene_num: int = 1, total_scenes: int = 1,
                     scene_context: str = "") -> bool:
    """
    Synthesise one scene to MP3. Used by external callers.
    Tries Gemini TTS first, then Cloud TTS.
    """
    return _synthesize_scene_file(text, voice_name, output_path, scene_num, total_scenes, scene_context)


def _synthesize_scene_file(text: str, voice_name: str, output_path: Path,
                            scene_num: int, total_scenes: int,
                            scene_context: str = "") -> bool:
    """Inner per-scene synthesiser: Gemini TTS → Cloud TTS fallback."""
    for attempt in range(1, 3):
        try:
            prompt = _build_scene_prompt(text, voice_name, scene_num, total_scenes, scene_context)
            pcm    = _gemini_raw_pcm(prompt, voice_name)
            _pcm_to_mp3(pcm, output_path)
            kb = output_path.stat().st_size / 1024
            logger.info(f"[TTS] Scene {scene_num}/{total_scenes}: {output_path.name} ({kb:.1f} KB)")
            return True

        except ImportError as e:
            logger.warning(f"Gemini TTS skipped (missing dependency): {e}")
            break
        except Exception as exc:
            logger.warning(f"Gemini TTS attempt {attempt}/2 failed: {exc}")
            if attempt == 1:
                time.sleep(3)

    return _cloud_tts_synthesize(text, voice_name, output_path)


# ── Cloud TTS fallback (original Chirp3-HD path) ─────────────────────────────

def _to_ssml(text: str) -> str:
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
    return "".join(ssml)


def _cloud_tts_synthesize(text: str, voice_name: str, output_path: Path) -> bool:
    from google.cloud import texttospeech
    from lib.cost_tracker import log_tts_call

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
            log_tts_call("chirp3-hd-telugu", char_count=len(text), stage="tts_generation")
            return True

        except Exception as exc:
            logger.warning(f"Cloud TTS attempt {attempt}/2 failed ({voice_name}): {exc}")
            if attempt == 1:
                time.sleep(2)

    raise RuntimeError(
        f"Cloud TTS failed for {output_path.name} after 2 attempts with {voice_name}."
    )
