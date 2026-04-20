import logging
import time
from pathlib import Path

from google.cloud import texttospeech

logger = logging.getLogger(__name__)

# All synthesis uses Chirp3-HD. No Standard fallback — quality drop is unacceptable.
# If Chirp3 fails: retry once with 2s backoff, then raise so generate.py skips the scene.


def synthesize_scene(text: str, voice_name: str, output_path: Path) -> bool:
    """Synthesize one scene to MP3. Retries once on failure, then raises.

    Args:
        text: Telugu narration text
        voice_name: full Chirp3-HD voice name (e.g. "te-IN-Chirp3-HD-Charon")
        output_path: destination .mp3 path
    Returns:
        True on success
    Raises:
        RuntimeError if both attempts fail
    """
    for attempt in range(1, 3):
        try:
            client = texttospeech.TextToSpeechClient()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
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
