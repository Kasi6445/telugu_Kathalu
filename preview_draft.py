#!/usr/bin/env python3
"""
preview_draft.py — Print a human-readable summary of a draft before promoting.

Usage:
  python preview_draft.py <timestamp>
  python preview_draft.py 20260420_153012
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"


def main():
    if len(sys.argv) != 2:
        print("Usage: python preview_draft.py <timestamp>")
        sys.exit(1)

    ts        = sys.argv[1]
    draft_dir = DRAFTS_DIR / ts
    story_file = draft_dir / "story.json"

    if not draft_dir.exists():
        print(f"Error: draft '{ts}' not found in drafts/")
        sys.exit(1)

    if not story_file.exists():
        print(f"Error: story.json missing in drafts/{ts}/")
        sys.exit(1)

    with open(story_file, "r", encoding="utf-8") as f:
        s = json.load(f)

    audio_files = sorted((draft_dir / "audio").glob("scene*.mp3")) if (draft_dir / "audio").exists() else []
    img_dir     = draft_dir / "images"
    image_files = (sorted(img_dir.glob("scene*.jpg")) + sorted(img_dir.glob("scene*.png"))) if img_dir.exists() else []

    print("\n" + "=" * 60)
    print(f"  DRAFT PREVIEW — {ts}")
    print("=" * 60)
    print(f"  Title      : {s.get('title', '—')}")
    print(f"  Category   : {s.get('category', '—')} / {s.get('subcategory', '—')}")
    print(f"  Topic      : {s.get('topic', '—')}")
    print(f"  Voice      : {s.get('voice', '—')}")
    print(f"  Date       : {s.get('date', '—')}")
    print(f"  Moral      : {s.get('moral', '—')}")
    print(f"  Audio files: {len(audio_files)}")
    print(f"  Image files: {len(image_files)}")
    print(f"  Scenes     : {len(s.get('scenes', []))}")
    print()

    for scene in s.get("scenes", []):
        print(f"  Scene {scene['id']}: {scene['text']}")
        print()

    incomplete = []
    if len(audio_files) != len(s.get("scenes", [])):
        incomplete.append(f"audio: {len(audio_files)}/{len(s.get('scenes', []))} files")
    if len(image_files) != len(s.get("scenes", [])):
        incomplete.append(f"images: {len(image_files)}/{len(s.get('scenes', []))} files")

    if incomplete:
        print(f"  ⚠️  Incomplete: {', '.join(incomplete)}")
    else:
        print("  ✅ All audio and images present")

    print()
    print(f"  Promote : python promote.py {ts}")
    print(f"  Reject  : python reject.py {ts}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
