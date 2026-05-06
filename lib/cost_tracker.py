"""
lib/cost_tracker.py — Per-call cost logging for all Gemini / Cloud TTS API calls.

Every API call that flows through make_client() is automatically intercepted by
CostTrackedClient and logged here. No per-module changes needed for basic tracking.

Exceptions that require one manual call each:
  - Google Cloud TTS Chirp3-HD  → log_tts_call() in lib/tts.py:_cloud_tts_synthesize()
  - Google Search grounding      → log_grounding_call() in tools/build_mythology_kb.py

Log file : logs/cost_audit.jsonl  (one JSON object per line)
Console  : prints a cost line after every call

JSONL schema (all calls use this unified structure):
  {
    "timestamp":               "2026-05-05T12:34:56.789+00:00",
    "model":                   "gemini-2.5-flash",
    "billing_unit":            "tokens" | "characters" | "grounded_queries",
    "input_count":             1200,           # tokens OR chars OR query count
    "output_count":            800,            # tokens only; null for TTS/grounding
    "cost_usd":                0.000330,
    "cumulative_session_usd":  0.42,
    "stage":                   "narration",    # set via set_stage() before the call
    "estimated_vertex_cost_usd": 0.035        # grounding records only
  }

Usage:
    from lib.cost_tracker import set_stage, log_tts_call, log_grounding_call, print_daily_summary

    set_stage("outline")          # call before a block of API calls; persists per-thread
    # ... make_client() calls are auto-tracked
    log_tts_call("chirp3-hd-telugu", char_count=5000)
    log_grounding_call(query_count=1)
    print_daily_summary()
"""

import json
import threading
from datetime import UTC, date, datetime
from pathlib import Path


# ── Pricing table ──────────────────────────────────────────────────────────────
#
# ⚠️  PRICING VERIFIED from official pages on 2026-05-05.
#     Re-verify before long production runs:
#       Vertex AI: https://cloud.google.com/vertex-ai/generative-ai/pricing
#       Cloud TTS: https://cloud.google.com/text-to-speech/pricing
#
# NOTE: Vertex AI prices for gemini-2.5-flash are HIGHER than AI Studio prices.
#   Vertex  → $0.30 input / $2.50 output per 1M tokens  (verified 2026-05-05)
#   AI Studio → ~$0.075 input / ~$0.30 output per 1M tokens (lower tier)
# The numbers below are Vertex AI prices since that's where production traffic routes.
# If you are running on AI Studio (GCP_PROJECT_ID not set), actual bills will be lower.

_INPUT_USD_PER_1M: dict[str, float] = {
    # Vertex AI verified 2026-05-05
    "gemini-2.5-flash":     0.30,
    "gemini-2.5-pro":       1.25,   # ≤200K context window
    "gemini-2.5-pro-200k":  2.50,   # >200K context window
}

_OUTPUT_USD_PER_1M: dict[str, float] = {
    # Vertex AI verified 2026-05-05
    "gemini-2.5-flash":     2.50,
    "gemini-2.5-pro":      10.00,   # ≤200K context window
    "gemini-2.5-pro-200k": 15.00,   # >200K context window
}

_TTS_USD_PER_CHAR: dict[str, float] = {
    # TODO: gemini-2.5-flash-preview-tts is NOT listed on the Vertex AI pricing page
    # (preview model, pricing TBD). Using user-provided estimate until officially listed.
    # Verify at: https://cloud.google.com/vertex-ai/generative-ai/pricing
    "gemini-2.5-flash-preview-tts": 0.000015,

    # Chirp3-HD Studio voice tier: $16.00 per 1M characters.
    # Source: web search result 2026-05-05 (TTS pricing page content was truncated).
    # Verify at: https://cloud.google.com/text-to-speech/pricing
    "chirp3-hd-telugu": 0.000016,
}

# Vertex AI Grounding with Google Search: $35 per 1,000 grounded prompts.
# Source: https://cloud.google.com/vertex-ai/generative-ai/pricing (verified 2026-05-05)
# Free daily limits: 10,000/day for Pro, 1,500/day for Flash.
# We keep KB builder on AI Studio where grounding is free, so this is only used for
# the "estimated_vertex_cost_usd" field in grounding records.
_GROUNDING_USD_PER_QUERY: float = 0.035  # $35 / 1000


# ── TTS cost ceiling ──────────────────────────────────────────────────────────
#
# Hard stop for the gemini-2.5-flash-preview-tts preview model, whose pricing is
# unverified and could be unexpectedly high.  The guard fires BEFORE the API call,
# so no charge is incurred when the ceiling is hit.
#
# Applies only to preview TTS models (model name contains "preview").
# Raise this constant if you intentionally need to go higher in a single session.
TTS_PREVIEW_CEILING_USD: float = 1.00


# ── Session state ──────────────────────────────────────────────────────────────

_session_total: float = 0.0
_tts_session_total: float = 0.0   # tracked separately for the TTS ceiling check
_session_lock = threading.Lock()
_stage_ctx = threading.local()   # per-thread stage label


# ── Stage context ──────────────────────────────────────────────────────────────

def set_stage(stage: str) -> None:
    """Set the current pipeline stage tag for subsequent cost log entries (per-thread)."""
    _stage_ctx.current = stage


def get_stage() -> str:
    return getattr(_stage_ctx, "current", "unknown")


def get_session_total() -> float:
    """Return the current session spend in USD (thread-safe snapshot)."""
    with _session_lock:
        return _session_total


# ── Internal helpers ───────────────────────────────────────────────────────────

def _logs_dir() -> Path:
    from lib.config import LOGS_DIR   # lazy import to avoid circular at module level
    return LOGS_DIR


def _append_record(record: dict) -> None:
    log_path = _logs_dir() / "cost_audit.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _resolve_model_key(model: str) -> str:
    """Map a full model ID to the closest pricing key."""
    # Try exact match first, then prefix match.
    if model in _INPUT_USD_PER_1M:
        return model
    for key in sorted(_INPUT_USD_PER_1M, key=len, reverse=True):
        if model.startswith(key):
            return key
    return model  # unknown — cost will be 0, flagged in output


def _compute_text_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = _resolve_model_key(model)
    if key not in _INPUT_USD_PER_1M:
        return 0.0
    return (
        (input_tokens  / 1_000_000) * _INPUT_USD_PER_1M[key]
        + (output_tokens / 1_000_000) * _OUTPUT_USD_PER_1M[key]
    )


def _extract_char_count(contents) -> int:
    """Best-effort character count extraction from generate_content contents arg."""
    if isinstance(contents, str):
        return len(contents)
    if isinstance(contents, (list, tuple)):
        total = 0
        for item in contents:
            if isinstance(item, str):
                total += len(item)
            elif hasattr(item, "text") and isinstance(item.text, str):
                total += len(item.text)
            else:
                try:
                    parts = item.parts  # may raise RuntimeError from property — caught below
                except Exception:
                    parts = []
                for part in (parts or []):
                    try:
                        text = getattr(part, "text", None)
                        if isinstance(text, str):
                            total += len(text)
                    except Exception:
                        pass  # malformed Part — skip silently
        return total
    return 0


# ── Public logging API ─────────────────────────────────────────────────────────

def log_text_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    stage: str | None = None,
) -> float:
    """Log a text-generation call. Returns cost in USD."""
    global _session_total
    cost = _compute_text_cost(model, input_tokens, output_tokens)
    known = _resolve_model_key(model) in _INPUT_USD_PER_1M
    flag  = "" if known else " [⚠ unknown model — $0 estimated]"

    with _session_lock:
        _session_total += cost
        cumulative = _session_total

    record = {
        "timestamp":              datetime.now(UTC).isoformat(),
        "model":                  model,
        "billing_unit":           "tokens",
        "input_count":            input_tokens,
        "output_count":           output_tokens,
        "cost_usd":               round(cost, 8),
        "cumulative_session_usd": round(cumulative, 6),
        "stage":                  stage or get_stage(),
    }
    _append_record(record)
    print(
        f"[COST] {record['stage']} | {model}{flag} | "
        f"in={input_tokens:,} out={output_tokens:,} tok | "
        f"${cost:.6f} | session=${cumulative:.4f}",
        flush=True,
    )
    return cost


def log_tts_call(
    model: str,
    char_count: int,
    stage: str | None = None,
) -> float:
    """Log a TTS call (character-based billing). Returns cost in USD."""
    global _session_total, _tts_session_total
    price = _TTS_USD_PER_CHAR.get(model, 0.0)
    cost  = char_count * price
    known = model in _TTS_USD_PER_CHAR
    flag  = "" if known else " [⚠ unknown TTS model — $0 estimated]"

    with _session_lock:
        _session_total     += cost
        _tts_session_total += cost
        cumulative = _session_total

    record = {
        "timestamp":              datetime.now(UTC).isoformat(),
        "model":                  model,
        "billing_unit":           "characters",
        "input_count":            char_count,
        "output_count":           None,
        "cost_usd":               round(cost, 8),
        "cumulative_session_usd": round(cumulative, 6),
        "stage":                  stage or get_stage(),
    }
    _append_record(record)
    print(
        f"[COST] {record['stage']} | {model}{flag} | "
        f"{char_count:,} chars | "
        f"${cost:.6f} | session=${cumulative:.4f}",
        flush=True,
    )
    return cost


def log_grounding_call(
    query_count: int = 1,
    stage: str | None = None,
) -> None:
    """Log Google Search grounding queries (AI Studio free tier — $0 billed).

    Records estimated_vertex_cost_usd so you can see what staying on Vertex would cost.
    """
    est_vertex = round(query_count * _GROUNDING_USD_PER_QUERY, 4)

    with _session_lock:
        cumulative = _session_total  # grounding is free — no delta, but read under lock

    record = {
        "timestamp":                datetime.now(UTC).isoformat(),
        "model":                    "gemini-2.5-pro+google-search",
        "billing_unit":             "grounded_queries",
        "input_count":              query_count,
        "output_count":             None,
        "cost_usd":                 0.0,
        "cumulative_session_usd":   round(cumulative, 6),
        "stage":                    stage or get_stage(),
        "estimated_vertex_cost_usd": est_vertex,
    }
    _append_record(record)
    print(
        f"[COST] {record['stage']} | google-search grounding | "
        f"{query_count} query | $0.00 (AI Studio free tier) | "
        f"Vertex equivalent: ${est_vertex:.3f}",
        flush=True,
    )


# ── Daily rollup ───────────────────────────────────────────────────────────────

def print_daily_summary(target_date: str | None = None) -> None:
    """Print today's (or target_date's) spend from cost_audit.jsonl, grouped by stage and model.

    Args:
        target_date: ISO date string "YYYY-MM-DD". Defaults to today (UTC).
    """
    log_path = _logs_dir() / "cost_audit.jsonl"
    if not log_path.exists():
        print("[COST SUMMARY] No cost_audit.jsonl found yet.")
        return

    day = target_date or date.today().isoformat()
    records: list[dict] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
                if r.get("timestamp", "").startswith(day):
                    records.append(r)
            except json.JSONDecodeError:
                continue

    if not records:
        print(f"[COST SUMMARY] No records for {day}.")
        return

    # ── Group by stage ──────────────────────────────────────────────────────────
    by_stage: dict[str, dict] = {}
    for r in records:
        s = r.get("stage", "unknown")
        entry = by_stage.setdefault(s, {"cost": 0.0, "calls": 0, "models": set()})
        entry["cost"]  += r.get("cost_usd", 0.0)
        entry["calls"] += 1
        entry["models"].add(r.get("model", "?"))

    # ── Group by model ──────────────────────────────────────────────────────────
    by_model: dict[str, float] = {}
    for r in records:
        m = r.get("model", "unknown")
        by_model[m] = by_model.get(m, 0.0) + r.get("cost_usd", 0.0)

    total = sum(r.get("cost_usd", 0.0) for r in records)
    total_calls = len(records)

    grounding_queries = sum(
        r.get("input_count", 0)
        for r in records
        if r.get("billing_unit") == "grounded_queries"
    )
    est_vertex_grounding = sum(
        r.get("estimated_vertex_cost_usd", 0.0)
        for r in records
        if r.get("billing_unit") == "grounded_queries"
    )

    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  Daily Cost Summary — {day}  ({total_calls} API calls)")
    print(sep)

    print("\n  By Stage (sorted by cost):")
    for stage, d in sorted(by_stage.items(), key=lambda x: -x[1]["cost"]):
        models = ", ".join(sorted(d["models"]))
        print(f"    {stage:<32} ${d['cost']:.5f}  ({d['calls']:>3} calls)  [{models}]")

    print("\n  By Model:")
    for model, cost in sorted(by_model.items(), key=lambda x: -x[1]):
        print(f"    {model:<48} ${cost:.5f}")

    print(f"\n  Total billed today : ${total:.5f}  (${total * 83:,.2f} INR approx)")
    if grounding_queries:
        print(f"  Search grounding   : {grounding_queries} queries  (AI Studio free tier)")
        print(f"  [Vertex equivalent : ${est_vertex_grounding:.3f}]")
    print(f"{sep}\n")


# ── Auto-tracking client wrapper ───────────────────────────────────────────────

class _TrackedModels:
    """Wraps genai.Client.models to intercept generate_content and log cost."""

    def __init__(self, real_models):
        self._real = real_models

    def generate_content(self, model: str, contents, config=None, **kwargs):
        # ── Pre-call TTS ceiling guard ────────────────────────────────────────
        # Runs BEFORE the API call so the charge is never incurred when the
        # ceiling is exceeded.  Only applied to preview TTS models.
        if _is_tts_model(model) and "preview" in model.lower():
            try:
                char_count = _extract_char_count(contents)
                estimated  = char_count * _TTS_USD_PER_CHAR.get(model, 0.0)
                with _session_lock:
                    projected = _tts_session_total + estimated
                if projected > TTS_PREVIEW_CEILING_USD:
                    raise RuntimeError(
                        f"[COST GUARD] TTS preview ceiling ${TTS_PREVIEW_CEILING_USD:.2f} "
                        f"would be exceeded (session so far=${_tts_session_total:.4f}, "
                        f"this call ~${estimated:.4f}). "
                        f"Raise TTS_PREVIEW_CEILING_USD in lib/cost_tracker.py to continue."
                    )
            except RuntimeError:
                raise   # re-raise ceiling errors
            except Exception:
                pass    # never let cost guard break non-ceiling errors

        response = self._real.generate_content(
            model=model, contents=contents, config=config, **kwargs
        )
        try:
            if _is_tts_model(model):
                char_count = _extract_char_count(contents)
                log_tts_call(model=model, char_count=char_count)
            else:
                usage = getattr(response, "usage_metadata", None)
                if usage and getattr(usage, "prompt_token_count", None) is not None:
                    log_text_call(
                        model=model,
                        input_tokens=usage.prompt_token_count or 0,
                        output_tokens=usage.candidates_token_count or 0,
                    )
                # If no usage_metadata (e.g. image generation models), silently skip.
        except Exception:
            # Cost tracking must NEVER break the pipeline.
            pass
        return response

    def __getattr__(self, name):
        return getattr(self._real, name)


def _is_tts_model(model: str) -> bool:
    return "tts" in model.lower()


class CostTrackedClient:
    """Thin wrapper around genai.Client that auto-logs cost after every generate_content.

    Returned by make_client() in lib/config.py when this module is importable.
    All other attributes are transparently delegated to the real client.
    """

    def __init__(self, real_client):
        self._real  = real_client
        self.models = _TrackedModels(real_client.models)

    def __getattr__(self, name):
        return getattr(self._real, name)
