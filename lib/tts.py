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

# Per-voice speech rate calibration (Telugu chars per second at natural narration pace).
# Slower voices (Enceladus, Iapetus, Charon) produce longer audio per character.
_VOICE_CHARS_PER_SEC: dict[str, float] = {
    # Measured from Gemini TTS output: Telugu produces ~10-13 chars/sec regardless
    # of "energy" classification. Higher-energy voices speak more expressively
    # (more pauses, more dynamics) so they are NOT faster in wall-clock terms.
    # Values calibrated from observed scene durations; old values were 2× too high
    # for energetic voices, causing systematic Gemini TTS sanity failures.
    "Achird":     11.0,   # measured: ~10.5 chars/sec across 6 scenes
    "Laomedeia":  11.0,   # similar energy profile to Achird — same estimate
    "Callirrhoe": 12.0,
    "Iapetus":    12.0,
    "Leda":       12.5,
    "Gacrux":     12.5,
    "Autonoe":    13.0,
    "Fenrir":     13.0,
    "Charon":     13.5,   # was passing before — keep close to old 14.0
    "Enceladus":  11.0,   # original calibration, kept
}
_DEFAULT_CHARS_PER_SEC = 16.0
_MIN_DURATION_RATIO    = 0.50   # < 50% of expected → TTS truncated the text
_MAX_DURATION_RATIO    = 1.75   # > 175% of expected → TTS repeated content
_MP3_BYTES_PER_SEC     = 128 * 1024 / 8  # 128 kbps → 16 000 bytes/s


def _audio_ok(path: Path, text: str, voice_name: str = "") -> bool:
    """Return False if audio is truncated (too short) or has repeated content (too long)."""
    short         = voice_name.split("-")[-1] if voice_name else ""
    chars_per_sec = _VOICE_CHARS_PER_SEC.get(short, _DEFAULT_CHARS_PER_SEC)
    expected_secs = len(text) / chars_per_sec
    actual_secs   = path.stat().st_size / _MP3_BYTES_PER_SEC

    if actual_secs < expected_secs * _MIN_DURATION_RATIO:
        logger.warning(
            f"Audio sanity FAIL {path.name}: truncated — "
            f"expected ~{expected_secs:.0f}s, got ~{actual_secs:.0f}s "
            f"({actual_secs/expected_secs:.2f}x) — will retry"
        )
        return False
    if actual_secs > expected_secs * _MAX_DURATION_RATIO:
        logger.warning(
            f"Audio sanity FAIL {path.name}: repeated content — "
            f"expected ~{expected_secs:.0f}s, got ~{actual_secs:.0f}s "
            f"({actual_secs/expected_secs:.2f}x) — will retry"
        )
        return False
    return True


# ── Voice style map ───────────────────────────────────────────────────────────

_VOICE_STYLE: dict[str, str] = {
    "Autonoe":    "a loving Telugu grandmother who tells stories with her whole heart — warm, melodic, full of life",
    "Gacrux":     "a wise village grandmother whose voice carries every emotion the story holds",
    "Callirrhoe": "a warm, emotionally expressive young aunt who makes children laugh, gasp, and lean in closer",
    "Leda":       "a gentle, melodic village storyteller whose voice rises and falls like a song",
    "Laomedeia":  "an animated, playful storyteller who acts out every character and pulls children into the world",
    "Iapetus":    "a thoughtful village elder — wise and warm, with a voice that holds both weight and tenderness",
    "Enceladus":  "a deep, commanding epic storyteller whose voice fills the listener with wonder and awe",
    "Fenrir":     "a strong, expressive narrator who performs an epic tale with power, pace, and presence",
    "Charon":     "a warm, confident Telugu storyteller — engaging and clear, with natural human rhythm",
    "Achird":     "an energetic, friendly narrator who brings every adventure to life with joy and personality",
}
_DEFAULT_STYLE = "a warm Telugu storyteller performing for children aged 5-8"


def _extract_voice_short(voice_name: str) -> str:
    """te-IN-Chirp3-HD-Kore  →  Kore"""
    return voice_name.split("-")[-1]


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_scene_prompt(text: str, voice_name: str,
                        scene_num: int = 1, total_scenes: int = 1,
                        scene_context: str = "") -> str:
    """Per-scene TTS prompt engineered for natural, human-like Telugu narration."""
    short = _extract_voice_short(voice_name)
    style = _VOICE_STYLE.get(short, _DEFAULT_STYLE)

    mood_line = ""
    if scene_context:
        mood_line = (
            f"THIS SCENE'S MOOD: {scene_context}\n"
            f"Let the mood live in your voice — not just your words:\n"
            f"  Tense / scary → voice drops a little, pace slows just slightly, breath tightens\n"
            f"  Exciting / joyful → voice lifts, a touch more energy, eyes bright\n"
            f"  Sad / tender → softer, slower, more intimate — like a secret between you and the child\n"
            f"  Wonder / surprise → voice opens up, then pulls back to almost a whisper\n"
            f"The child must FEEL what is happening before the meaning even registers.\n\n"
        )

    return (
        f"You are {style}. Right now, you are telling this Telugu story "
        f"to a group of 6-year-old children sitting in a circle around you, "
        f"looking up at you with wide, trusting eyes.\n\n"

        f"You are already mid-story — you have been speaking for the past minute "
        f"and the children are completely with you. Continue from the very first word below "
        f"with full warmth, full character, full engagement. "
        f"No introduction. No announcement. Just the story, flowing naturally.\n\n"

        f"{mood_line}"

        f"EMOTION — the single most important thing:\n"
        f"You are not reading text. You are LIVING this story and bringing the children "
        f"inside it with you. Every sentence must carry real feeling — "
        f"your pitch rises with excitement, softens with tenderness, quickens with urgency, "
        f"drops with suspense. A monotone voice loses children instantly. "
        f"Flat is failure. Human emotion is everything.\n\n"

        f"PACE — alive, not laggy:\n"
        f"The natural pace of a teacher who loves this story and knows it by heart. "
        f"Fast enough that children stay fully awake. Slow enough that every Telugu word "
        f"lands clearly. Never dragging. Never rushing. Never flat. "
        f"Think: you are performing, not reciting.\n\n"

        f"EMOTION = PAUSE — the only rule for breathing:\n"
        f"Before every pause, ask: does the EMOTION demand a breath here?\n"
        f"  Suspense, reveal, shock, tenderness → YES, breathe here.\n"
        f"  Normal narration continuing the same scene → NO, keep flowing.\n"
        f"Punctuation does NOT automatically mean pause. "
        f"A period between two sentences that are part of the same unfolding thought "
        f"gets NO pause — just flow straight through it with natural voice energy.\n\n"

        f"TARGET RHYTHM — this is your concrete goal:\n"
        f"Aim for 2–4 seconds of continuous flowing speech between breaths. "
        f"If you are pausing more often than every 2 seconds, you are pausing too much. "
        f"Group consecutive sentences that belong to the same emotional moment "
        f"into ONE flowing breath. Breathe only when the emotion shifts.\n\n"

        f"THOUGHT GROUPS — speak complete thoughts, not individual sentences:\n"
        f"A thought group is everything that belongs to the same emotional beat — "
        f"it might span 2-3 short sentences. Speak the whole group in one arc.\n"
        f"  , comma        → NO pause. Flow straight through, commas are connectors not stops.\n"
        f"  — em-dash      → short dramatic beat, then immediately back into the story\n"
        f"  ... three dots → one suspense breath — child leans forward — then continue\n"
        f"  । or . end     → only pause if the NEXT sentence is a different emotional beat. "
        f"If it continues the same thought, ride straight through the period.\n"
        f"  Dialogue       → shift into the character's voice, return to narrator after the quote\n\n"

        f"WHAT IMMERSIVE NARRATION SOUNDS LIKE:\n"
        f"  ✗ 'He entered the room. (pause) He looked around. (pause) He saw something strange.'\n"
        f"  ✓ 'He entered the room and looked around — and saw something strange.'\n"
        f"  ✗ Pause at every period — choppy, sounds like careful reading\n"
        f"  ✓ Flow through periods when emotion is the same — sounds like living the story\n\n"

        f"PITCH & TONE — how to make narration cinematic:\n"
        f"Your pitch is your most powerful tool. Use it exactly like this:\n"
        f"  CURIOSITY / QUESTION  → raise pitch slightly on the final words — voice lifts, "
        f"like you yourself want to know the answer\n"
        f"  SUSPENSE / DANGER     → drop pitch lower, slow pace just slightly — "
        f"voice tightens, like you are afraid to say what comes next\n"
        f"  TENDER / EMOTIONAL    → soften to near-whisper, more intimate — "
        f"like you are sharing a secret with each child personally\n"
        f"  REVEAL / SHOCK        → slow down on the key word, add slight weight — "
        f"pause before it, then land it clearly: 'అది... పాము!'\n"
        f"  JOY / TRIUMPH         → lift pitch throughout the sentence, more energy — "
        f"your voice smiles and the children smile with you\n"
        f"  NORMAL NARRATION      → warm, even, at natural speaking energy — "
        f"not flat, but not performative either\n"
        f"The target: children must FEEL the emotion before they understand the words. "
        f"Stable monotone pitch = children fall asleep. Cinematic pitch variation = "
        f"children sit up and lean in.\n\n"

        f"PRONUNCIATION:\n"
        f"Every Telugu syllable fully formed and crisp. "
        f"Children are learning language through listening — "
        f"make every word a clear, beautiful gift to them.\n\n"

        f"CONSISTENCY: Same warmth, same character, same voice — "
        f"scene {scene_num} of {total_scenes}. The children have been listening since scene 1. "
        f"Do not break the spell.\n\n"

        f"Read the text below exactly once, word for word, and stop the moment it ends. "
        f"Do not repeat, paraphrase, or add anything.\n\n"

        f"{text}"
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
    for attempt in range(1, 4):  # up to 3 attempts (extra one for sanity-check retry)
        try:
            prompt = _build_scene_prompt(text, voice_name, scene_num, total_scenes, scene_context)
            pcm    = _gemini_raw_pcm(prompt, voice_name)
            _pcm_to_mp3(pcm, output_path)

            if not _audio_ok(output_path, text, voice_name):
                output_path.unlink(missing_ok=True)
                raise RuntimeError("Audio sanity check failed — truncated or repeated content")

            kb = output_path.stat().st_size / 1024
            logger.info(f"[TTS] Scene {scene_num}/{total_scenes}: {output_path.name} ({kb:.1f} KB)")
            return True

        except ImportError as e:
            logger.warning(f"Gemini TTS skipped (missing dependency): {e}")
            break
        except Exception as exc:
            logger.warning(f"Gemini TTS attempt {attempt}/3 failed: {exc}")
            if attempt < 3:
                time.sleep(3)

    return _cloud_tts_synthesize(text, voice_name, output_path)


# ── Cloud TTS fallback (original Chirp3-HD path) ─────────────────────────────

def _to_ssml(text: str) -> str:
    # Pause philosophy: "one thought = one breath"
    # Strategic pauses only — em-dash (drama), ellipsis (suspense), sentence end (breath).
    # Commas: NO pause — the narrator flows through them as part of the same thought.
    # Short sentences flow together; only true sentence-end punctuation gets a breath.
    segment_re = re.compile(r"(—|\.\.\.|\n\s*\n)")
    raw_segments = segment_re.split(text)

    ssml = ["<speak>"]
    for seg in raw_segments:
        if seg == "—":
            ssml.append('<break time="500ms"/>')    # dramatic beat — shorter, snappier
        elif seg == "...":
            ssml.append('<break time="700ms"/>')    # suspense breath — child leans forward
        elif re.match(r"\n\s*\n", seg):
            ssml.append('<break time="400ms"/>')
        else:
            escaped = html.escape(seg.strip())
            if not escaped:
                continue
            escaped = re.sub(r"([!])([\s])", r'\1<break time="250ms"/>\2', escaped)
            escaped = re.sub(r"([?])([\s])", r'\1<break time="300ms"/>\2', escaped)
            escaped = re.sub(r"([.।])([\s])", r'\1<break time="300ms"/>\2', escaped)
            # Commas: zero added pause — narrator treats them as connectors, not stops
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
