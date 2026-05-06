#!/usr/bin/env python3
"""
scripts/check_routing.py — Pre-flight routing validator.

Checks that the environment is correctly configured for Vertex AI routing
before running any story generation or smoke tests.  Makes NO API calls.

Usage:
    python scripts/check_routing.py

Exit codes:
    0 — all checks passed (safe to proceed)
    1 — one or more checks failed (fix before running live calls)
"""

import json
import os
import sys
from pathlib import Path

# -- Ensure project root is on path --------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# dotenv must load before importing lib.config
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# -- Helpers --------------------------------------------------------------------

PASS = "  [OK] "
FAIL = "  [FAIL] "
WARN = "  [WARN] "
SEP  = "=" * 62


def _check(label: str, ok: bool, detail: str, fix: str = "") -> bool:
    prefix = PASS if ok else FAIL
    print(f"{prefix}{label}")
    if detail:
        print(f"        {detail}")
    if not ok and fix:
        print(f"        Fix: {fix}")
    return ok


# -- Routing checks ------------------------------------------------------------─

def check_env_vars() -> bool:
    gcp   = os.getenv("GCP_PROJECT_ID", "")
    loc   = os.getenv("GCP_LOCATION",   "us-central1")
    allow = os.getenv("ALLOW_AI_STUDIO","false").lower()
    key   = os.getenv("GEMINI_API_KEY", "")

    ok_project = bool(gcp)
    ok_key     = bool(key)
    ok_loc     = loc == "us-central1"

    _check("GCP_PROJECT_ID set",    ok_project, f"value: {gcp or '(empty)'}",
           "Set GCP_PROJECT_ID in .env to your GCP project ID")
    _check("GCP_LOCATION=us-central1", ok_loc,
           f"value: {loc}  (asia-south1 lacks preview TTS + Imagen)",
           "Set GCP_LOCATION=us-central1 in .env")
    _check("GEMINI_API_KEY set (AI Studio fallback)", ok_key,
           f"value: {'(set)' if key else '(empty)'}")

    allow_ok = allow in ("true", "false")
    is_true  = allow == "true"
    _check(
        "ALLOW_AI_STUDIO=false (safety guard active)",
        not is_true,
        f"value: {allow}",
        "Remove ALLOW_AI_STUDIO=true or set to false — it should only be true during local dev without GCP"
        if is_true else "",
    )
    return ok_project and ok_loc


def check_routing_mode() -> bool:
    """Import lib.config and confirm which routing path will activate."""
    try:
        import lib.config as cfg
        if cfg.GCP_PROJECT_ID:
            print(f"{PASS}Routing mode: Vertex AI")
            print(f"        project  = {cfg.GCP_PROJECT_ID}")
            print(f"        location = {cfg.GCP_LOCATION}")
            return True
        elif cfg.ALLOW_AI_STUDIO:
            print(f"{WARN}Routing mode: AI Studio (ALLOW_AI_STUDIO=true)")
            print(f"        This is OK for local dev but NOT for production credit runs.")
            return False
        else:
            print(f"{FAIL}Routing mode: BLOCKED (no GCP_PROJECT_ID and ALLOW_AI_STUDIO!=true)")
            print(f"        make_client() will raise RuntimeError on any API call.")
            return False
    except Exception as exc:
        print(f"{FAIL}Could not import lib.config: {exc}")
        return False


def check_adc() -> bool:
    """Check whether Application Default Credentials file exists."""
    adc_candidates = [
        Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json",
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json",
    ]
    adc_path = next((p for p in adc_candidates if p.exists()), None)

    if adc_path:
        try:
            data    = json.loads(adc_path.read_text(encoding="utf-8"))
            acct    = data.get("client_email") or data.get("account") or "(service account)"
            # For user credentials the key is "account" inside a "credentials" dict
            if "credentials" in data:
                acct = data["credentials"].get("account", acct)
        except Exception:
            acct = "(could not parse)"
        return _check(
            "Application Default Credentials (ADC) found",
            True,
            f"file: {adc_path}\n        account: {acct}",
        )
    else:
        return _check(
            "Application Default Credentials (ADC) found",
            False,
            "ADC file not found in any standard location",
            "Run: gcloud auth application-default login",
        )


def check_no_bypasses() -> bool:
    """Scan Python source for any remaining genai.Client(api_key=) outside allowed files."""
    ALLOWED_BYPASSES = {
        "lib/config.py",              # fallback path inside make_client() itself
        "tools/build_mythology_kb.py",   # intentional AI Studio exception
        "scripts/check_routing.py",   # this file — contains the pattern as a string literal
    }

    violations: list[tuple[str, int, str]] = []
    for py_file in ROOT.rglob("*.py"):
        rel = py_file.relative_to(ROOT).as_posix()
        if any(rel == a for a in ALLOWED_BYPASSES):
            continue
        try:
            for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if "genai.Client(api_key=" in line:
                    violations.append((rel, lineno, line.strip()))
        except Exception:
            pass

    if violations:
        print(f"{FAIL}Hardcoded genai.Client(api_key=...) bypasses found:")
        for path, lineno, line in violations:
            print(f"        {path}:{lineno}  →  {line}")
        return False
    else:
        return _check("No hardcoded API-key client bypasses", True,
                      "All modules use make_client() — Vertex AI routing is enforced")


def check_cost_tracker() -> bool:
    """Confirm cost_tracker.py is importable and TTS ceiling is set."""
    try:
        import lib.cost_tracker as ct
        ceiling = ct.TTS_PREVIEW_CEILING_USD
        return _check(
            "lib/cost_tracker.py importable",
            True,
            f"TTS_PREVIEW_CEILING_USD = ${ceiling:.2f}",
        )
    except Exception as exc:
        return _check("lib/cost_tracker.py importable", False, str(exc))


def check_logs_dir() -> bool:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    return _check("logs/ directory exists", True, str(logs))


# -- Main ----------------------------------------------------------------------─

def main() -> int:
    print(f"\n{SEP}")
    print("  Vertex AI Routing Pre-flight Check")
    print(SEP)

    results: list[bool] = []

    print("\n-- Environment variables ----------------------------------")
    results.append(check_env_vars())

    print("\n-- Routing mode (lib/config.py) ---------------------------")
    results.append(check_routing_mode())

    print("\n-- Application Default Credentials ------------------------")
    results.append(check_adc())

    print("\n-- Client bypass scan -------------------------------------")
    results.append(check_no_bypasses())

    print("\n-- Cost tracker -------------------------------------------")
    results.append(check_cost_tracker())

    print("\n-- Logs directory -----------------------------------------")
    results.append(check_logs_dir())

    passed = sum(results)
    total  = len(results)
    failed = total - passed

    print(f"\n{SEP}")
    if failed == 0:
        print(f"  RESULT: ALL {total} checks passed — safe to run smoke test")
        print(SEP + "\n")
        return 0
    else:
        print(f"  RESULT: {failed}/{total} checks FAILED — fix before proceeding")
        print(SEP + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
