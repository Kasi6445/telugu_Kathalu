#!/usr/bin/env python3
"""
scripts/test_tts_cache.py — Verify the TTS cache check costs $0.00.

Copies an existing story's audio folder to a temp location under drafts/,
then runs synthesize_story() against the copy.  Every scene must be skipped
with "[TTS CACHE] scene N reused — $0.00".  No TTS API calls are made.

The original stories/ folder is never touched.

Usage:
    python scripts/test_tts_cache.py
    python scripts/test_tts_cache.py --story stories/20260516_201204
"""

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from lib.config import DRAFTS_DIR
from lib.cost_tracker import get_session_total

DEFAULT_STORY = ROOT / "stories" / "20260516_201204"
TEMP_DIR      = DRAFTS_DIR / "cache_test_temp"


def main():
    parser = argparse.ArgumentParser(description="TTS cache check — zero-spend test")
    parser.add_argument(
        "--story", metavar="PATH",
        default=str(DEFAULT_STORY),
        help="Path to the promoted story folder (must contain story.json and audio/)",
    )
    args = parser.parse_args()

    story_dir = Path(args.story)
    src_audio = story_dir / "audio"
    story_json = story_dir / "story.json"

    SEP = "=" * 60

    # ── Validate source ───────────────────────────────────────────────────────
    if not story_json.exists():
        print(f"[ERROR] story.json not found at {story_json}")
        sys.exit(1)
    if not src_audio.is_dir():
        print(f"[ERROR] audio/ folder not found at {src_audio}")
        sys.exit(1)

    src_mp3s = sorted(src_audio.glob("scene*.mp3"))
    if not src_mp3s:
        print(f"[ERROR] No scene*.mp3 files found in {src_audio}")
        sys.exit(1)

    print(f"\n{SEP}")
    print("  TTS Cache Test — zero-spend verification")
    print(SEP)
    print(f"  Source story : {story_dir}")
    print(f"  Scene files  : {len(src_mp3s)} MP3s")
    print(f"  Temp copy    : {TEMP_DIR}")
    print(f"  Live stories/: NEVER WRITTEN")

    # ── Load story.json ───────────────────────────────────────────────────────
    story = json.loads(story_json.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    voice  = story.get("voice", "te-IN-Chirp3-HD-Laomedeia")

    if not scenes:
        print("[ERROR] story.json has no scenes array.")
        sys.exit(1)

    # ── Copy audio to temp location ───────────────────────────────────────────
    def _force_remove(action, path, exc):
        os.chmod(path, stat.S_IWRITE)
        action(path)

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, onerror=_force_remove)
    temp_audio = TEMP_DIR / "audio"
    shutil.copytree(src_audio, temp_audio)
    print(f"\n  Copied {len(src_mp3s)} MP3s → {temp_audio}")

    # ── Run synthesize_story() against the copy ───────────────────────────────
    print(f"\n{SEP}")
    print("  Running synthesize_story() — expect all cache hits:")
    print(SEP)

    tts_before = get_session_total()

    from lib.tts import synthesize_story
    synthesize_story(scenes, voice, temp_audio)

    tts_spend = get_session_total() - tts_before

    # ── Validate result ───────────────────────────────────────────────────────
    print(f"\n{SEP}")
    if tts_spend == 0.0:
        print(f"  PASS — TTS cost: $0.00  (all {len(scenes)} scenes served from cache)")
    else:
        print(f"  FAIL — TTS cost: ${tts_spend:.6f}  (expected $0.00)")
        print("         At least one scene triggered a live API call.")
        print("         Check that scene IDs in story.json match the MP3 filenames.")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    try:
        shutil.rmtree(TEMP_DIR, onerror=_force_remove)
        print(f"  Temp folder removed: {TEMP_DIR}")
    except Exception as e:
        print(f"  [WARN] Could not remove temp folder ({e}) — delete manually: {TEMP_DIR}")
    print(SEP + "\n")

    sys.exit(0 if tts_spend == 0.0 else 1)


if __name__ == "__main__":
    main()
