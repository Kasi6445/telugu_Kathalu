import html
import logging
import re
import time
from pathlib import Path

from google.cloud import texttospeech

logger = logging.getLogger(__name__)

# Chirp3-HD supports: <speak>, <break>, <p>, <s>
# It does NOT support: <prosody pitch/rate>, <emphasis>
# Our strategy: drive prosody through SSML <break> tags + punctuation in the text itself.


def _to_ssml(text: str) -> str:
    """Convert Telugu narration to SSML with strategic pauses.

    Pause markers written by story_gen:
      —   (em-dash)  → 650ms dramatic pause, storyteller leaning in
      ... (ellipsis) → 900ms suspense pause, child holding breath
      !              → 350ms after exclamation (excitement, then land)
      ?              → 450ms after question (let it hang)
      .              → 500ms sentence pause (natural breath)
      Blank line     → 800ms paragraph gap (scene shift)
    """
    # Split on explicit pause markers first (before XML-escaping)
    # Pattern: em-dash OR ellipsis OR blank line
    segment_re = re.compile(r'(—|\.\.\.|\n\s*\n)')
    raw_segments = segment_re.split(text)

    ssml = ['<speak>']

    for seg in raw_segments:
        if seg == '—':
            ssml.append('<break time="650ms"/>')
        elif seg == '...':
            ssml.append('<break time="900ms"/>')
        elif re.match(r'\n\s*\n', seg):
            ssml.append('<break time="800ms"/>')
        else:
            # Escape XML special chars
            escaped = html.escape(seg.strip())
            if not escaped:
                continue

            # Add pauses after sentence-ending punctuation (followed by space or end)
            # Order matters: longer patterns first
            escaped = re.sub(r'([!])([\s])', r'\1<break time="350ms"/>\2', escaped)
            escaped = re.sub(r'([?])([\s])', r'\1<break time="450ms"/>\2', escaped)
            escaped = re.sub(r'([.।])([\s])', r'\1<break time="500ms"/>\2', escaped)

            # Comma → micro-pause (keeps phrases distinct, stops word-merge)
            escaped = re.sub(r'([,])([\s])', r'\1<break time="150ms"/>\2', escaped)

            ssml.append(escaped)

    ssml.append('</speak>')
    result = ''.join(ssml)
    logger.debug(f"SSML ({len(result)} chars): {result[:120]}...")
    return result


def synthesize_scene(text: str, voice_name: str, output_path: Path) -> bool:
    """Synthesize one scene to MP3 using SSML for prosody control.

    Args:
        text: Telugu narration text (may contain —, ..., punctuation as prosody cues)
        voice_name: full Chirp3-HD voice name (e.g. "te-IN-Chirp3-HD-Charon")
        output_path: destination .mp3 path
    Returns:
        True on success
    Raises:
        RuntimeError if both attempts fail
    """
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
                # Chirp3-HD does NOT support pitch or speaking_rate — omit entirely
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    sample_rate_hertz=22050,
                ),
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.audio_content)
            kb = len(response.audio_content) / 1024
            logger.info(f"TTS OK: {output_path.name} ({kb:.1f} KB) voice={voice_name}")
            return True

        except Exception as exc:
            logger.warning(f"TTS attempt {attempt}/2 failed ({voice_name}): {exc}")
            if attempt == 1:
                logger.info("Retrying in 2s...")
                time.sleep(2)

    raise RuntimeError(
        f"TTS failed for {output_path.name} after 2 attempts with {voice_name}. "
        f"Check ADC credentials and Chirp3-HD availability."
    )
