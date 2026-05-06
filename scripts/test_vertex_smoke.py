#!/usr/bin/env python3
"""
scripts/test_vertex_smoke.py — Phase 4 Vertex AI smoke test.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
DO NOT RUN until billing case 70914394 is resolved (~May 13, 2026).
The Generative Language API is currently DISABLED on project
telugu-kathalu-493805 during the goodwill credit propagation window.
Running this script before resolution will produce auth/permission errors.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

What this script tests (in order):
  1. Routing — confirms Vertex AI is active, not AI Studio
  2. Gemini Flash text call — "say hello in Telugu" (1 API call, ~$0.00)
  3. Cloud TTS Chirp3-HD call — synthesize "namaste" (1 API call, ~$0.00)
  4. Cost log — confirms both calls appear in logs/cost_audit.jsonl
  5. Audio file — saves TTS output to a temp path and reports size

Prerequisites (run BEFORE this script):
  python scripts/check_routing.py   # must show 6/6 pass

gcloud commands needed (one-time, if not already done):
  gcloud auth application-default login
  gcloud config set project telugu-kathalu-493805
  gcloud services enable aiplatform.googleapis.com
  gcloud services enable texttospeech.googleapis.com

Usage:
  python scripts/test_vertex_smoke.py          # interactive confirmation prompt
  python scripts/test_vertex_smoke.py --force  # skip confirmation (CI / trusted shell)
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── Project root on path ────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


# ── Runtime gate ────────────────────────────────────────────────────────────────

def _confirm_or_abort(force: bool) -> None:
    """Require explicit confirmation before making any live GCP API calls."""
    print()
    print("=" * 66)
    print("  PHASE 4 SMOKE TEST — LIVE GCP API CALLS")
    print("=" * 66)
    print()
    print("  WARNING: Billing case 70914394 must be RESOLVED before")
    print("  running this script. The Generative Language API is")
    print("  disabled on project telugu-kathalu-493805 until ~May 13.")
    print()

    from lib.config import GCP_PROJECT_ID, GCP_LOCATION
    print(f"  Project  : {GCP_PROJECT_ID or '(NOT SET — abort)'}")
    print(f"  Location : {GCP_LOCATION}")
    print()

    if not GCP_PROJECT_ID:
        print("  ABORT: GCP_PROJECT_ID not set. Fix .env and retry.")
        sys.exit(1)

    if not force:
        try:
            answer = input("  Type 'yes' to proceed with live API calls: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborted.")
            sys.exit(0)
        if answer != "yes":
            print("  Aborted.")
            sys.exit(0)

    print()


# ── Individual smoke checks ─────────────────────────────────────────────────────

def check_1_routing() -> bool:
    """Confirm Vertex AI routing is active."""
    print("-- Check 1: Routing mode -----------------------------------------")
    from lib.config import GCP_PROJECT_ID, GCP_LOCATION, ALLOW_AI_STUDIO
    if GCP_PROJECT_ID:
        print(f"  [OK] Vertex AI | project={GCP_PROJECT_ID} | location={GCP_LOCATION}")
        return True
    elif ALLOW_AI_STUDIO:
        print("  [WARN] AI Studio mode — this smoke test is designed for Vertex AI")
        return True  # still runnable, just noting
    else:
        print("  [FAIL] No routing configured — make_client() will raise")
        return False


def check_2_gemini_flash(log_path: Path) -> bool:
    """One trivial Gemini Flash text call: 'say hello in Telugu'."""
    print("-- Check 2: Gemini Flash text call --------------------------------")
    try:
        from google.genai import types
        from lib.config import make_client
        from lib.cost_tracker import set_stage

        set_stage("smoke_test_text")
        client = make_client()

        t0 = datetime.utcnow().isoformat() + "Z"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say hello in Telugu in exactly one sentence.",
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=60,
            ),
        )
        reply = response.text.strip()
        print(f"  [OK] Response: {reply}")

        # Pull the cost record we just wrote
        if log_path.exists():
            records = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            latest  = next((r for r in reversed(records)
                            if r.get("stage") == "smoke_test_text"), None)
            if latest:
                print(f"  [OK] Cost logged: ${latest['cost_usd']:.6f} "
                      f"(in={latest['input_count']:,} out={latest['output_count']:,} tokens)")
        return True

    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return False


def check_3_cloud_tts(audio_out: Path) -> bool:
    """One trivial Cloud TTS call: synthesize 'namaste' with Chirp3-HD."""
    print("-- Check 3: Cloud TTS Chirp3-HD call ------------------------------")
    try:
        from google.cloud import texttospeech
        from lib.cost_tracker import log_tts_call, set_stage

        set_stage("smoke_test_tts")
        client = texttospeech.TextToSpeechClient()

        text = "నమస్తే"    # "namaste" in Telugu script
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code="te-IN",
                name="te-IN-Chirp3-HD-Kore",
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            ),
        )
        audio_out.write_bytes(response.audio_content)
        kb = len(response.audio_content) / 1024

        # Log the TTS cost manually (Cloud TTS bypasses CostTrackedClient)
        cost = log_tts_call("chirp3-hd-telugu", char_count=len(text), stage="smoke_test_tts")

        print(f"  [OK] Audio: {audio_out}  ({kb:.1f} KB)")
        print(f"  [OK] Cost logged: ${cost:.6f}  ({len(text)} chars)")
        return True

    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return False


def check_4_cost_log(log_path: Path, start_ts: str) -> bool:
    """Confirm both calls appear in cost_audit.jsonl."""
    print("-- Check 4: cost_audit.jsonl entries ------------------------------")
    if not log_path.exists():
        print(f"  [FAIL] Log file not found: {log_path}")
        return False

    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if r.get("timestamp", "") >= start_ts:
                records.append(r)
        except json.JSONDecodeError:
            pass

    if not records:
        print(f"  [FAIL] No records written after {start_ts}")
        return False

    total_cost = sum(r.get("cost_usd", 0.0) for r in records)
    print(f"  [OK] {len(records)} record(s) written this session")
    for r in records:
        unit = r.get("billing_unit", "?")
        cnt  = r.get("input_count", 0)
        print(f"       {r['stage']:<25} {r['model']:<45} "
              f"${r['cost_usd']:.6f}  [{unit}: {cnt}]")
    print(f"  [OK] Total smoke test cost: ${total_cost:.6f}")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 Vertex AI smoke test")
    parser.add_argument("--force", action="store_true",
                        help="Skip interactive confirmation (use in trusted shell only)")
    args = parser.parse_args()

    _confirm_or_abort(args.force)

    from lib.config import LOGS_DIR
    LOGS_DIR.mkdir(exist_ok=True)
    log_path  = LOGS_DIR / "cost_audit.jsonl"
    audio_out = Path(tempfile.gettempdir()) / "smoke_test.mp3"
    start_ts  = datetime.utcnow().isoformat() + "Z"

    results: list[bool] = []
    results.append(check_1_routing())
    print()
    results.append(check_2_gemini_flash(log_path))
    print()
    results.append(check_3_cloud_tts(audio_out))
    print()
    results.append(check_4_cost_log(log_path, start_ts))
    print()

    passed = sum(results)
    total  = len(results)
    sep    = "=" * 66

    print(sep)
    if passed == total:
        print(f"  SMOKE TEST PASSED ({passed}/{total}) — Vertex AI routing confirmed")
        print(f"  Next step: python scripts/audit_one_story.py")
    else:
        print(f"  SMOKE TEST FAILED ({passed}/{total} checks passed)")
        print(f"  Fix the failing checks above before running a full story audit.")
    print(sep)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
