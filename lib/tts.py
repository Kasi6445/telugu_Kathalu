"""
lib/tts.py — Expressive TTS for Telugu Katalu.

Primary  : Gemini 2.5 Flash TTS — full-story single call.
           The entire story is synthesised in ONE API call so the narrator
           voice stays identical across all scenes. The resulting PCM audio
           is split at silence boundaries to produce per-scene MP3 files.

Fallback : If the single-call split fails (not enough silence detected),
           falls back to per-scene calls with a strong baseline-voice anchor.

Last-resort fallback: Google Cloud TTS Chirp3-HD.

Audio pipeline (Gemini path):
  Gemini TTS → PCM bytes → silence split → per-scene MP3 (lameenc, no ffmpeg)
"""

import html
import logging
import re
import struct
import time
from pathlib import Path

logger = logging.getLogger(__name__)

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_SAMPLE_RATE = 24000   # Hz — Gemini TTS PCM output rate

# Separator injected between scenes in the full-story call.
# Gemini TTS reads "[SCENE BREAK]" as a cue to pause ~1-2 seconds.
_SCENE_SEP = "\n\n[SCENE BREAK]\n\n"


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


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_full_story_prompt(scene_texts: list[str], voice_name: str) -> str:
    """
    Prompt for the full-story single TTS call.
    All scenes joined with [SCENE BREAK] markers.
    Instructs the model to hold a single consistent voice throughout.
    """
    short  = _extract_voice_short(voice_name)
    style  = _VOICE_STYLE.get(short, _DEFAULT_STYLE)
    n      = len(scene_texts)
    joined = _SCENE_SEP.join(scene_texts)

    return (
        f"You are {style} recording a complete {n}-part Telugu audiobook "
        f"in ONE single continuous take — like a live radio performance. "
        f"VOICE CONSISTENCY — ABSOLUTE RULE: Your base pitch, speaking pace, "
        f"and vocal character must stay IDENTICAL from the first word to the very last. "
        f"A listener playing all parts back-to-back must hear ONE continuous narrator — "
        f"not a different tone in each part. "
        f"At each [SCENE BREAK] marker: take a natural 2-second breath pause, "
        f"then continue in the EXACT SAME voice. Do not reset your tone. "
        f"Emotional moments: use subtle pace changes only — NEVER shift your pitch baseline. "
        f"Character dialogue (words in quotes): give a brief distinct voice for that character, "
        f"then return to YOUR narrator baseline immediately after the quote ends. "
        f"The narrator voice never changes — only dialogue voices change temporarily.\n\n"
        f"Telugu story — {n} parts:\n\n{joined}"
    )


def _build_scene_prompt(text: str, voice_name: str,
                        scene_num: int = 1, total_scenes: int = 1) -> str:
    """Fallback per-scene prompt with strong baseline anchor."""
    short = _extract_voice_short(voice_name)
    style = _VOICE_STYLE.get(short, _DEFAULT_STYLE)

    return (
        f"You are {style} recording scene {scene_num} of {total_scenes} "
        f"in one continuous audiobook session. "
        f"VOICE CONSISTENCY: Your base pitch, pace, and vocal character are FIXED — "
        f"identical to every other scene in this story. Do not adjust your baseline. "
        f"Emotional moments: subtle pace change only — never a pitch shift. "
        f"Character dialogue (quotes): brief distinct voice, return to YOUR baseline immediately.\n\n"
        f"Telugu story scene:\n\n{text}"
    )


# ── PCM silence detection and splitting ──────────────────────────────────────

def _find_split_points(pcm: bytes, n_scenes: int,
                       rate: int = _SAMPLE_RATE) -> list[int]:
    """
    Locate the n_scenes-1 longest silence regions in PCM audio and return
    their midpoint byte offsets as split points.

    Uses 10ms frames, RMS amplitude threshold, and minimum 300ms silence.
    Returns [] if fewer silence regions than needed are found.
    """
    needed = n_scenes - 1
    if needed <= 0:
        return []

    FRAME_SAMPLES = rate // 100          # 10ms = 240 samples at 24kHz
    FRAME_BYTES   = FRAME_SAMPLES * 2    # 16-bit = 2 bytes/sample
    THRESHOLD     = 250                  # RMS below this = silent
    MIN_FRAMES    = 30                   # 300ms minimum silence duration

    total_samples = len(pcm) // 2
    n_frames      = total_samples // FRAME_SAMPLES

    # Mark each 10ms frame as silent or not
    is_silent: list[bool] = []
    for i in range(n_frames):
        offset = i * FRAME_BYTES
        count  = min(FRAME_SAMPLES, total_samples - i * FRAME_SAMPLES)
        if count <= 0:
            break
        chunk = struct.unpack_from(f"{count}h", pcm, offset)
        rms   = (sum(s * s for s in chunk) // count) ** 0.5
        is_silent.append(rms < THRESHOLD)

    # Collect contiguous silence regions as (length_frames, mid_byte_offset)
    regions: list[tuple[int, int]] = []
    in_silence  = False
    silence_start = 0

    for i, silent in enumerate(is_silent):
        if silent and not in_silence:
            in_silence    = True
            silence_start = i
        elif not silent and in_silence:
            in_silence = False
            length = i - silence_start
            if length >= MIN_FRAMES:
                mid = (silence_start + i) // 2
                regions.append((length, mid * FRAME_BYTES))

    if in_silence:
        length = n_frames - silence_start
        if length >= MIN_FRAMES:
            mid = (silence_start + n_frames) // 2
            regions.append((length, mid * FRAME_BYTES))

    if len(regions) < needed:
        logger.warning(
            f"[TTS SPLIT] Found {len(regions)} silence region(s), need {needed}. "
            f"Falling back to per-scene synthesis."
        )
        return []

    # Pick the needed longest regions, return sorted by position
    regions.sort(key=lambda x: x[0], reverse=True)
    split_points = sorted(pos for _, pos in regions[:needed])
    logger.info(f"[TTS SPLIT] {len(split_points)} split point(s) found at bytes {split_points}")
    return split_points


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


# ── Gemini TTS — full-story single call ──────────────────────────────────────

def _gemini_raw_pcm(prompt: str, voice_name: str) -> bytes:
    """Make one Gemini TTS call and return raw PCM bytes."""
    from google import genai
    from google.genai import types
    from lib.config import GEMINI_API_KEY

    short_voice = _extract_voice_short(voice_name)
    client      = genai.Client(api_key=GEMINI_API_KEY)

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
    raw  = part.inline_data.data

    if isinstance(raw, str):
        import base64
        raw = base64.b64decode(raw)

    return raw


# ── Public API ────────────────────────────────────────────────────────────────

def synthesize_story(scenes: list[dict], voice_name: str, audio_dir: Path) -> None:
    """
    Synthesise the ENTIRE story in ONE Gemini TTS call for a consistent narrator
    voice across all scenes. Splits the resulting PCM at silence boundaries to
    produce individual per-scene MP3 files.

    Falls back to per-scene synthesis (with baseline-voice anchor) if:
      - The full-story call fails (API error, quota).
      - Silence detection cannot find enough split points.

    Args:
        scenes:     story["scenes"] list — each dict must have "id" and "text".
        voice_name: Full Chirp3-HD voice name (e.g. "te-IN-Chirp3-HD-Fenrir").
        audio_dir:  Directory to write scene1.mp3, scene2.mp3, …
    """
    n    = len(scenes)
    ids  = [s["id"]   for s in scenes]
    texts = [s["text"] for s in scenes]

    audio_dir.mkdir(parents=True, exist_ok=True)

    if n == 1:
        _synthesize_scene_file(texts[0], voice_name,
                               audio_dir / f"scene{ids[0]}.mp3", 1, 1)
        return

    # ── Attempt: full story in one call ──────────────────────────────────────
    print(f"  [TTS] Generating all {n} scenes in one call (voice consistency)...", flush=True)

    try:
        prompt = _build_full_story_prompt(texts, voice_name)
        pcm    = _gemini_raw_pcm(prompt, voice_name)

        split_points = _find_split_points(pcm, n)

        if split_points:
            # Split PCM → save each segment as MP3
            segments: list[bytes] = []
            prev = 0
            for pos in split_points:
                segments.append(pcm[prev:pos])
                prev = pos
            segments.append(pcm[prev:])

            if len(segments) == n:
                for seg_pcm, scene_id in zip(segments, ids):
                    out = audio_dir / f"scene{scene_id}.mp3"
                    _pcm_to_mp3(seg_pcm, out)
                    kb = out.stat().st_size / 1024
                    logger.info(f"[TTS] Full-story segment saved: {out.name} ({kb:.1f} KB)")
                print(f"  [TTS] ✓ {n} scenes split and saved from single call.", flush=True)
                return

            logger.warning(
                f"[TTS SPLIT] Segment count {len(segments)} != {n} — falling back."
            )

    except ImportError:
        raise
    except Exception as exc:
        logger.warning(f"[TTS] Full-story call failed: {exc} — falling back to per-scene.")
        print(f"  [TTS] Full-story call failed — switching to per-scene synthesis.", flush=True)

    # ── Fallback: per-scene with baseline anchor ──────────────────────────────
    print(f"  [TTS] Per-scene fallback ({n} individual calls)...", flush=True)
    for idx, scene in enumerate(scenes, start=1):
        _synthesize_scene_file(
            scene["text"], voice_name,
            audio_dir / f"scene{scene['id']}.mp3",
            idx, n,
        )


def synthesize_scene(text: str, voice_name: str, output_path: Path,
                     scene_num: int = 1, total_scenes: int = 1) -> bool:
    """
    Synthesise one scene to MP3. Used by the fallback path and external callers.
    Tries Gemini TTS first, then Cloud TTS.
    """
    return _synthesize_scene_file(text, voice_name, output_path, scene_num, total_scenes)


def _synthesize_scene_file(text: str, voice_name: str, output_path: Path,
                            scene_num: int, total_scenes: int) -> bool:
    """Inner per-scene synthesiser: Gemini TTS → Cloud TTS fallback."""
    for attempt in range(1, 3):
        try:
            prompt = _build_scene_prompt(text, voice_name, scene_num, total_scenes)
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
                time.sleep(2)

    raise RuntimeError(
        f"Cloud TTS failed for {output_path.name} after 2 attempts with {voice_name}."
    )
