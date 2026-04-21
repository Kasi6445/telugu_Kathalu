#!/usr/bin/env python3
"""
reject.py — Delete a draft that should not be promoted.

Usage:
  python reject.py <timestamp>
  python reject.py 20260420_153012
"""
import os
import shutil
import stat
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR   = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"


def main():
    if len(sys.argv) != 2:
        print("Usage: python reject.py <timestamp>")
        sys.exit(1)

    ts        = sys.argv[1]
    draft_dir = DRAFTS_DIR / ts

    if not draft_dir.exists():
        print(f"Error: draft '{ts}' not found in drafts/")
        sys.exit(1)

    # Show what will be deleted
    files = list(draft_dir.rglob("*"))
    print(f"\nAbout to delete drafts/{ts}/ ({len(files)} files)")
    confirm = input("Confirm? [y/N] ").strip().lower()

    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    def _force_remove(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(draft_dir, onexc=_force_remove)
    print(f"🗑️  Deleted drafts/{ts}/\n")


if __name__ == "__main__":
    main()
