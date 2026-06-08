"""
scripts/audit_all_stories.py

Comprehensive audit of every story — checks:
  1. Thumbnail URL format (https:// vs relative)
  2. R2 has ALL expected scene images + audio (via boto3 HEAD)
  3. Thumbnail URL actually returns HTTP 200

Categories:
  GOOD          — R2 URLs in story.json AND all files exist in R2
  MISSING_FILES — R2 URLs in story.json but some files missing from R2
  BAD_URL       — story.json still has relative/missing thumbnail path

Required env vars (load from .env automatically):
  R2_ACCOUNT_ID
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
  R2_BUCKET_NAME

Usage:
  python scripts/audit_all_stories.py
"""

import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# ── Load .env ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

R2_BASE_URL = os.environ.get(
    "R2_BASE_URL",
    "https://pub-558b12062e854257a35815cd84959ad0.r2.dev",
)

# ── R2 client ──────────────────────────────────────────────────────────────────

def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def key_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchKey", "403"):
            return False
        raise


def http_ok(url: str) -> tuple[bool, int]:
    """Return (success, status_code). Treats non-200 as failure."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200, resp.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, 0


# ── Story helpers ──────────────────────────────────────────────────────────────

def load_index() -> list[dict]:
    with open(ROOT / "stories" / "index.json", encoding="utf-8") as f:
        return json.load(f)["stories"]


def load_story_json(story_id: str) -> dict | None:
    path = ROOT / "stories" / story_id / "story.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


# ── Per-story audit ────────────────────────────────────────────────────────────

def audit_story(entry: dict, client, bucket: str) -> dict:
    story_id = entry["id"]
    slug = entry.get("slug", story_id)

    # -- Read story.json for scene count
    story = load_story_json(story_id)
    if story is None:
        return {
            "id": story_id,
            "slug": slug,
            "status": "NO_LOCAL_JSON",
            "scene_count": None,
            "thumbnail": entry.get("thumbnail", ""),
            "missing": [],
            "thumbnail_http_status": None,
        }

    scenes = story.get("scenes", story.get("slides", []))
    scene_count = len(scenes)
    thumbnail = story.get("thumbnail", "")

    # -- Check thumbnail URL format
    if not thumbnail or not thumbnail.startswith("https://"):
        return {
            "id": story_id,
            "slug": slug,
            "status": "BAD_URL",
            "scene_count": scene_count,
            "thumbnail": thumbnail,
            "missing": [],
            "thumbnail_http_status": None,
        }

    # -- Check all expected R2 keys
    missing = []
    for i in range(1, scene_count + 1):
        img_key = f"stories/{story_id}/images/scene{i}.jpg"
        aud_key = f"stories/{story_id}/audio/scene{i}.mp3"
        if not key_exists(client, bucket, img_key):
            missing.append(img_key)
        if not key_exists(client, bucket, aud_key):
            missing.append(aud_key)

    # -- HTTP GET thumbnail to confirm 200
    ok, http_status = http_ok(thumbnail)

    if missing:
        status = "MISSING_FILES"
    elif not ok:
        status = "THUMBNAIL_404"
    else:
        status = "GOOD"

    return {
        "id": story_id,
        "slug": slug,
        "status": status,
        "scene_count": scene_count,
        "thumbnail": thumbnail,
        "missing": missing,
        "thumbnail_http_status": http_status,
    }


# ── Git history check ──────────────────────────────────────────────────────────

def check_git_history(missing_keys: list[str]) -> dict[str, bool]:
    """Check if each file path ever existed in git history."""
    import subprocess
    result = {}
    for key in missing_keys:
        local_path = str(ROOT / key).replace("\\", "/")
        # Try both the R2 key path and the local stories/ path
        proc = subprocess.run(
            ["git", "log", "--all", "--oneline", "--", key, f"stories/{key.split('stories/')[-1]}"],
            capture_output=True, text=True, cwd=ROOT
        )
        result[key] = bool(proc.stdout.strip())
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Validate env
    for var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
        if not os.environ.get(var):
            print(f"ERROR: {var} env var is not set. Check your .env file.")
            sys.exit(1)

    bucket = os.environ["R2_BUCKET_NAME"]
    client = get_r2_client()

    stories = load_index()
    total = len(stories)
    print(f"Auditing {total} stories against R2 bucket '{bucket}' ...\n")
    print("(This checks {n} R2 objects + {n} HTTP requests — may take a few minutes)\n".format(
        n=f"~{total * 10}"
    ))

    results = []
    completed = 0

    # Use threads: boto3 head_object is I/O bound, parallelism helps a lot
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(audit_story, entry, client, bucket): entry
            for entry in stories
        }
        for fut in as_completed(futures):
            completed += 1
            r = fut.result()
            results.append(r)
            # Progress tick every 10 stories
            if completed % 10 == 0 or completed == total:
                good = sum(1 for x in results if x["status"] == "GOOD")
                bad = sum(1 for x in results if x["status"] != "GOOD")
                print(f"  [{completed}/{total}] GOOD={good}  ISSUES={bad}", flush=True)

    # Sort by story_id for deterministic output
    results.sort(key=lambda r: r["id"])

    # ── Categorize ─────────────────────────────────────────────────────────────
    good          = [r for r in results if r["status"] == "GOOD"]
    bad_url       = [r for r in results if r["status"] == "BAD_URL"]
    missing_files = [r for r in results if r["status"] == "MISSING_FILES"]
    thumb_404     = [r for r in results if r["status"] == "THUMBNAIL_404"]
    no_json       = [r for r in results if r["status"] == "NO_LOCAL_JSON"]

    print("\n" + "=" * 70)
    print("AUDIT REPORT")
    print("=" * 70)
    print(f"  Total stories checked : {total}")
    print(f"  GOOD                  : {len(good)}")
    print(f"  MISSING_FILES (R2)    : {len(missing_files)}")
    print(f"  THUMBNAIL_404 (HTTP)  : {len(thumb_404)}")
    print(f"  BAD_URL (relative)    : {len(bad_url)}")
    print(f"  NO_LOCAL_JSON         : {len(no_json)}")
    print("=" * 70)

    # ── GOOD ───────────────────────────────────────────────────────────────────
    if good:
        print(f"\nGOOD ({len(good)} stories) — all files in R2, thumbnail returns 200")
        for r in good:
            print(f"  OK  {r['id']}  [{r['slug']}]  scenes={r['scene_count']}")

    # ── BAD_URL ────────────────────────────────────────────────────────────────
    if bad_url:
        print(f"\nBAD_URL ({len(bad_url)} stories) — story.json has relative/missing thumbnail path")
        for r in bad_url:
            print(f"  BAD  {r['id']}  [{r['slug']}]  thumbnail={r['thumbnail']!r}")

    # ── THUMBNAIL_404 ──────────────────────────────────────────────────────────
    if thumb_404:
        print(f"\nTHUMBNAIL_404 ({len(thumb_404)} stories) — URL is set but HTTP returns non-200")
        for r in thumb_404:
            print(f"  404  {r['id']}  [{r['slug']}]  http={r['thumbnail_http_status']}  url={r['thumbnail']}")

    # ── MISSING_FILES ──────────────────────────────────────────────────────────
    if missing_files:
        print(f"\nMISSING_FILES ({len(missing_files)} stories) — R2 URL set but files absent from R2")

        # Collect all missing keys for git history check
        all_missing_keys = []
        for r in missing_files:
            all_missing_keys.extend(r["missing"])

        print(f"  Checking git history for {len(all_missing_keys)} missing files ...", flush=True)
        git_history = check_git_history(all_missing_keys)

        for r in missing_files:
            print(f"\n  MISS  {r['id']}  [{r['slug']}]  scenes={r['scene_count']}  missing={len(r['missing'])} files")
            for key in r["missing"]:
                in_git = git_history.get(key, False)
                tag = "  (was in git history)" if in_git else "  (NEVER in git)"
                print(f"        {key}{tag}")

    # ── NO_LOCAL_JSON ─────────────────────────────────────────────────────────
    if no_json:
        print(f"\nNO_LOCAL_JSON ({len(no_json)} stories) — story.json missing locally (index.json only)")
        for r in no_json:
            print(f"  NOJSON  {r['id']}  [{r['slug']}]")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    issues = len(missing_files) + len(bad_url) + len(thumb_404) + len(no_json)
    if issues == 0:
        print("ALL CLEAR — every story is healthy.")
        sys.exit(0)
    else:
        print(f"ACTION NEEDED — {issues} stories have issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()
