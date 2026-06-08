"""
scripts/backfill_focal_points.py

Detect thumbnail focal points for all existing stories that lack one.
Downloads scene1.jpg from R2 (the thumbnail URL in each entry), detects
the focal point, then updates stories/index.json and stories/<id>/story.json.

Run from project root:
    python scripts/backfill_focal_points.py
"""
import io
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from lib.image_gen import detect_thumbnail_focal_point

INDEX_FILE   = ROOT / "stories" / "index.json"
STORIES_DIR  = ROOT / "stories"


def _focal_from_url(url: str) -> tuple[int, int]:
    """Download a JPEG from url into memory and detect its focal point."""
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = resp.read()
    tmp = io.BytesIO(data)
    # Write to a temp file because PIL can read from BytesIO but
    # detect_thumbnail_focal_point expects a Path — wrap it.
    from PIL import Image
    import numpy as np
    img = Image.open(tmp).convert("RGB").resize((100, 150), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32)
    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1]))
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    saliency = gy + gx
    h, w = saliency.shape
    xs = np.arange(w)[None, :]
    ys = np.arange(h)[:, None]
    center_weight = 1.0 - 0.3 * np.sqrt(((xs - w / 2) / w) ** 2 + ((ys - h / 2) / h) ** 2)
    saliency *= center_weight
    threshold = np.percentile(saliency, 80)
    ys_m, xs_m = np.where(saliency >= threshold)
    x_pct = int(round(float(xs_m.mean()) / w * 100))
    y_pct = int(round(float(ys_m.mean()) / h * 100))
    return x_pct, y_pct


def run():
    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)

    stories = index["stories"]
    updated = 0
    failed  = 0

    for entry in stories:
        if entry.get("thumbnail_focal_point"):
            continue

        sid       = entry["id"]
        thumbnail = entry.get("thumbnail", "")

        if not thumbnail:
            print(f"  skip {sid} — no thumbnail URL")
            failed += 1
            continue

        try:
            x, y = _focal_from_url(thumbnail)
        except Exception as e:
            print(f"  FAIL {sid} — {e}")
            failed += 1
            continue

        fp = {"x": x, "y": y}
        entry["thumbnail_focal_point"] = fp

        # Also patch the individual story.json if it exists locally
        story_file = STORIES_DIR / sid / "story.json"
        if story_file.exists():
            with open(story_file, encoding="utf-8") as f:
                story = json.load(f)
            story["thumbnail_focal_point"] = fp
            tmp = story_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(story, f, ensure_ascii=False, indent=2)
            shutil.move(str(tmp), str(story_file))

        print(f"  {sid}: ({x}%, {y}%)")
        updated += 1

    # Write updated index
    tmp = INDEX_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    shutil.move(str(tmp), str(INDEX_FILE))

    print(f"\nDone — updated {updated} stories, failed/skipped {failed}.")


if __name__ == "__main__":
    run()
