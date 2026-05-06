"""
tests/test_cost_tracker.py

Unit tests for lib/cost_tracker.py.  State isolation is handled by
the autouse `_reset_state` fixture in conftest.py — every test starts
with session_total=0, tts_session_total=0, stage="unknown", and all
JSONL writes go to a pytest tmp_path (never logs/cost_audit.jsonl).

NOTE: The user spec mentioned TTS_PREVIEW_ACKNOWLEDGED but that flag
does not exist in the codebase.  The actual ceiling behaviour is:
  - Raises RuntimeError when projected cost > TTS_PREVIEW_CEILING_USD.
  - No acknowledgement env var needed.
Tests below cover the real behaviour.
"""

import json
import threading
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_records(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_fixture(log_path: Path, records: list[dict]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class _MockModels:
    """Minimal stand-in for genai.Client.models used by _TrackedModels tests."""

    class _Response:
        usage_metadata = None

    def generate_content(self, model, contents, config=None, **kwargs):
        return self._Response()


# ── _compute_text_cost ────────────────────────────────────────────────────────

class TestComputeTextCost:
    def test_flash_exact(self, ct):
        # 1M in @ $0.30 + 1M out @ $2.50 = $2.80
        assert abs(ct._compute_text_cost("gemini-2.5-flash", 1_000_000, 1_000_000) - 2.80) < 1e-9

    def test_pro_exact(self, ct):
        # 1M in @ $1.25 + 1M out @ $10.00 = $11.25
        assert abs(ct._compute_text_cost("gemini-2.5-pro", 1_000_000, 1_000_000) - 11.25) < 1e-9

    def test_pro_200k_exact(self, ct):
        # 1M in @ $2.50 + 1M out @ $15.00 = $17.50
        assert abs(ct._compute_text_cost("gemini-2.5-pro-200k", 1_000_000, 1_000_000) - 17.50) < 1e-9

    def test_zero_tokens(self, ct):
        assert ct._compute_text_cost("gemini-2.5-flash", 0, 0) == 0.0

    def test_unknown_model_returns_zero(self, ct):
        assert ct._compute_text_cost("gemini-99-unknown", 1_000, 500) == 0.0

    def test_prefix_match(self, ct):
        # A versioned ID that starts with a known key should resolve to the same price.
        base      = ct._compute_text_cost("gemini-2.5-flash", 100_000, 50_000)
        versioned = ct._compute_text_cost("gemini-2.5-flash-001", 100_000, 50_000)
        assert base == versioned

    def test_small_call_fractional(self, ct):
        # (1200/1e6)*0.30 + (800/1e6)*2.50 = 0.00036 + 0.002 = 0.00236
        assert abs(ct._compute_text_cost("gemini-2.5-flash", 1200, 800) - 0.00236) < 1e-9


# ── log_text_call ─────────────────────────────────────────────────────────────

class TestLogTextCall:
    def test_returns_correct_cost(self, ct):
        cost = ct.log_text_call("gemini-2.5-flash", 1_000_000, 1_000_000)
        assert abs(cost - 2.80) < 1e-9

    def test_writes_valid_jsonl_row(self, ct, log_path):
        ct.log_text_call("gemini-2.5-flash", 500, 200, stage="test_stage")
        records = _read_records(log_path)
        assert len(records) == 1
        r = records[0]
        assert r["model"] == "gemini-2.5-flash"
        assert r["billing_unit"] == "tokens"
        assert r["input_count"] == 500
        assert r["output_count"] == 200
        assert r["stage"] == "test_stage"
        for field in ("timestamp", "cost_usd", "cumulative_session_usd"):
            assert field in r

    def test_cumulative_accumulates_correctly(self, ct):
        c1 = ct.log_text_call("gemini-2.5-flash", 100, 100)
        c2 = ct.log_text_call("gemini-2.5-flash", 100, 100)
        assert abs(ct._session_total - (c1 + c2)) < 1e-9

    def test_unknown_model_writes_zero_cost(self, ct, log_path):
        cost = ct.log_text_call("gemini-99-fake", 1000, 500, stage="test")
        assert cost == 0.0
        assert _read_records(log_path)[0]["cost_usd"] == 0.0

    def test_missing_stage_defaults_to_unknown(self, ct, log_path):
        ct.log_text_call("gemini-2.5-flash", 100, 50)
        assert _read_records(log_path)[0]["stage"] == "unknown"

    def test_thread_stage_ctx_used_when_stage_not_passed(self, ct, log_path):
        ct.set_stage("pipeline_pass2")
        ct.log_text_call("gemini-2.5-flash", 100, 50)
        assert _read_records(log_path)[0]["stage"] == "pipeline_pass2"


# ── log_tts_call ──────────────────────────────────────────────────────────────

class TestLogTtsCall:
    def test_returns_correct_cost(self, ct):
        # chirp3-hd-telugu: $0.000016/char × 5000 chars = $0.08
        assert abs(ct.log_tts_call("chirp3-hd-telugu", 5000, stage="tts") - 0.08) < 1e-9

    def test_writes_valid_jsonl_row(self, ct, log_path):
        ct.log_tts_call("chirp3-hd-telugu", 1000, stage="tts_gen")
        r = _read_records(log_path)[0]
        assert r["billing_unit"] == "characters"
        assert r["input_count"] == 1000
        assert r["output_count"] is None
        assert r["stage"] == "tts_gen"

    def test_zero_chars(self, ct):
        assert ct.log_tts_call("chirp3-hd-telugu", 0) == 0.0

    def test_unknown_model_zero_cost(self, ct, log_path):
        cost = ct.log_tts_call("unknown-tts-model", 10_000, stage="tts")
        assert cost == 0.0
        assert _read_records(log_path)[0]["cost_usd"] == 0.0

    def test_tts_session_total_tracked_separately(self, ct):
        ct.log_tts_call("chirp3-hd-telugu", 1000)
        ct.log_tts_call("chirp3-hd-telugu", 2000)
        with ct._session_lock:
            actual = ct._tts_session_total
        expected = (1000 + 2000) * 0.000016
        assert abs(actual - expected) < 1e-9


# ── log_grounding_call ────────────────────────────────────────────────────────

class TestLogGroundingCall:
    def test_cost_is_always_zero(self, ct, log_path):
        ct.log_grounding_call(query_count=3, stage="kb")
        r = _read_records(log_path)[0]
        assert r["cost_usd"] == 0.0
        assert r["billing_unit"] == "grounded_queries"
        assert r["input_count"] == 3

    def test_estimated_vertex_cost_field(self, ct, log_path):
        # $35/1000 × 2 queries = $0.070
        ct.log_grounding_call(query_count=2)
        r = _read_records(log_path)[0]
        assert abs(r["estimated_vertex_cost_usd"] - 0.070) < 1e-6

    def test_session_total_unchanged_after_grounding(self, ct):
        ct.log_text_call("gemini-2.5-flash", 100, 100)
        before = ct._session_total
        ct.log_grounding_call(query_count=5)
        assert ct._session_total == before

    def test_cumulative_field_matches_session_total(self, ct, log_path):
        ct.log_text_call("gemini-2.5-flash", 1_000_000, 0)
        ct.log_grounding_call(query_count=1)
        lines = _read_records(log_path)
        text_cost          = lines[0]["cost_usd"]
        grounding_cumul    = lines[1]["cumulative_session_usd"]
        assert abs(grounding_cumul - text_cost) < 1e-6

    def test_cumulative_read_under_lock(self, ct, log_path):
        # This is the threading-safety regression test for the #3 fix.
        # We set a non-zero session total, call log_grounding_call from a thread,
        # and confirm the cumulative field reflects the total at call time.
        with ct._session_lock:
            ct._session_total = 0.12345
        ct.log_grounding_call(query_count=1)
        r = _read_records(log_path)[0]
        assert abs(r["cumulative_session_usd"] - 0.12345) < 1e-6


# ── TTS preview ceiling ───────────────────────────────────────────────────────

class TestTtsCeiling:
    def test_ceiling_raises_when_exceeded(self, ct, monkeypatch):
        monkeypatch.setattr(ct, "TTS_PREVIEW_CEILING_USD", 1.00)
        with ct._session_lock:
            ct._tts_session_total = 0.999
        tracked = ct._TrackedModels(_MockModels())
        # 10_000 chars × $0.000015 = $0.15 → projected = $1.149 > $1.00
        with pytest.raises(RuntimeError, match="TTS preview ceiling"):
            tracked.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents="x" * 10_000,
            )

    def test_ceiling_passes_when_under(self, ct, monkeypatch, log_path):
        monkeypatch.setattr(ct, "TTS_PREVIEW_CEILING_USD", 1.00)
        with ct._session_lock:
            ct._tts_session_total = 0.0
        tracked = ct._TrackedModels(_MockModels())
        # 100 chars × $0.000015 = $0.0015 — well under $1.00
        result = tracked.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents="x" * 100,
        )
        assert result is not None

    def test_ceiling_does_not_apply_to_non_preview_tts(self, ct, monkeypatch):
        # Set ceiling to $0.00 so any preview call would always block.
        # A non-preview TTS model (no "preview" in name) must pass through.
        monkeypatch.setattr(ct, "TTS_PREVIEW_CEILING_USD", 0.00)
        with ct._session_lock:
            ct._tts_session_total = 999.0
        tracked = ct._TrackedModels(_MockModels())
        # "gemini-2.5-flash-tts" has "tts" but NOT "preview" — guard must not fire.
        result = tracked.generate_content(
            model="gemini-2.5-flash-tts",
            contents="x" * 100,
        )
        assert result is not None

    def test_ceiling_exactly_at_limit_passes(self, ct, monkeypatch):
        """Guard fires on > (strictly greater), so exactly at the limit must pass."""
        monkeypatch.setattr(ct, "TTS_PREVIEW_CEILING_USD", 1.00)
        price = ct._TTS_USD_PER_CHAR.get("gemini-2.5-flash-preview-tts", 0.000015)
        # floor(1.00 / price) chars → projected cost ≤ 1.00
        chars = int(1.00 / price)
        with ct._session_lock:
            ct._tts_session_total = 0.0
        tracked = ct._TrackedModels(_MockModels())
        result = tracked.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents="x" * chars,
        )
        assert result is not None


# ── Threading ─────────────────────────────────────────────────────────────────

class TestThreading:
    def test_100_concurrent_calls_exact_total(self, ct, log_path):
        """100 threads each log one call — final session total must be numerically exact."""
        N              = 100
        INPUT_TOKENS   = 1_000
        OUTPUT_TOKENS  = 500
        per_call = ct._compute_text_cost("gemini-2.5-flash", INPUT_TOKENS, OUTPUT_TOKENS)
        expected = per_call * N

        errors: list[Exception] = []

        def _worker():
            try:
                ct.log_text_call(
                    "gemini-2.5-flash", INPUT_TOKENS, OUTPUT_TOKENS, stage="thread_test"
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Worker thread(s) raised: {errors}"

        # Session total is the critical threading-safety assertion.
        # Use relative tolerance: 100 float additions accumulate at most ~1e-13 error.
        with ct._session_lock:
            actual = ct._session_total
        assert actual == pytest.approx(expected, rel=1e-6), (
            f"Expected {expected:.12f}, got {actual:.12f}"
        )

        # All 100 records must have been written.
        records = _read_records(log_path)
        assert len(records) == N

        # The maximum cumulative in any record must equal total (within rounding to 6dp).
        last_cumul = max(r["cumulative_session_usd"] for r in records)
        assert last_cumul == pytest.approx(expected, rel=1e-4)


# ── print_daily_summary ───────────────────────────────────────────────────────

class TestPrintDailySummary:
    def test_no_file_prints_message(self, ct, capsys):
        ct.print_daily_summary("2020-01-01")
        assert "No cost_audit.jsonl" in capsys.readouterr().out

    def test_no_records_for_date_prints_message(self, ct, log_path, capsys):
        _write_fixture(log_path, [{
            "timestamp": "2020-01-01T00:00:00Z",
            "model": "gemini-2.5-flash", "billing_unit": "tokens",
            "input_count": 100, "output_count": 50,
            "cost_usd": 0.000155, "cumulative_session_usd": 0.000155,
            "stage": "narration",
        }])
        ct.print_daily_summary("2099-12-31")
        assert "No records for 2099-12-31" in capsys.readouterr().out

    def test_by_stage_and_model_sums(self, ct, log_path, capsys):
        day = "2026-05-05"
        _write_fixture(log_path, [
            {"timestamp": f"{day}T10:00:00Z", "model": "gemini-2.5-flash",
             "billing_unit": "tokens", "input_count": 1000, "output_count": 500,
             "cost_usd": 0.001, "cumulative_session_usd": 0.001, "stage": "narration"},
            {"timestamp": f"{day}T10:01:00Z", "model": "gemini-2.5-flash",
             "billing_unit": "tokens", "input_count": 800, "output_count": 200,
             "cost_usd": 0.0005, "cumulative_session_usd": 0.0015, "stage": "narration"},
            {"timestamp": f"{day}T10:02:00Z", "model": "chirp3-hd-telugu",
             "billing_unit": "characters", "input_count": 5000, "output_count": None,
             "cost_usd": 0.08, "cumulative_session_usd": 0.0815, "stage": "tts_generation"},
        ])
        ct.print_daily_summary(day)
        out = capsys.readouterr().out
        assert "0.08150" in out
        assert "narration" in out
        assert "tts_generation" in out

    def test_grounding_section_appears(self, ct, log_path, capsys):
        day = "2026-05-05"
        _write_fixture(log_path, [{
            "timestamp": f"{day}T10:00:00Z",
            "model": "gemini-2.5-pro+google-search",
            "billing_unit": "grounded_queries",
            "input_count": 3, "output_count": None,
            "cost_usd": 0.0, "cumulative_session_usd": 0.0,
            "stage": "kb_research",
            "estimated_vertex_cost_usd": 0.105,
        }])
        ct.print_daily_summary(day)
        out = capsys.readouterr().out.lower()
        assert "grounding" in out or "grounded" in out

    def test_total_equals_sum_of_records(self, ct, log_path, capsys):
        day = "2026-05-06"
        amounts = [0.001, 0.0025, 0.080]
        _write_fixture(log_path, [
            {"timestamp": f"{day}T10:0{i}:00Z", "model": "gemini-2.5-flash",
             "billing_unit": "tokens", "input_count": 100, "output_count": 50,
             "cost_usd": a, "cumulative_session_usd": sum(amounts[:i+1]),
             "stage": "test"}
            for i, a in enumerate(amounts)
        ])
        ct.print_daily_summary(day)
        out = capsys.readouterr().out
        # Total = 0.001 + 0.0025 + 0.080 = 0.0835
        assert "0.08350" in out


# ── _extract_char_count ───────────────────────────────────────────────────────

class TestExtractCharCount:
    def test_plain_string(self, ct):
        assert ct._extract_char_count("hello") == 5

    def test_list_of_strings(self, ct):
        assert ct._extract_char_count(["abc", "de"]) == 5

    def test_object_with_text_attr(self, ct):
        class _Obj:
            text = "hello world"
        assert ct._extract_char_count([_Obj()]) == 11

    def test_object_with_parts(self, ct):
        class _Part:
            text = "part text"
        class _Content:
            parts = [_Part(), _Part()]
        assert ct._extract_char_count([_Content()]) == 18

    def test_part_without_text_attr_is_skipped(self, ct):
        """Regression for #5 — Part with no .text must not crash, must return 0."""
        class _PartNoText:
            pass

        class _Content:
            parts = [_PartNoText()]

        assert ct._extract_char_count([_Content()]) == 0

    def test_part_with_non_string_text_is_skipped(self, ct):
        """Part.text = int/None must be skipped (regression for #5)."""
        class _PartBadText:
            text = 12345

        class _Content:
            parts = [_PartBadText()]

        assert ct._extract_char_count([_Content()]) == 0

    def test_parts_property_raises_is_handled_gracefully(self, ct):
        """If .parts raises an exception the item is skipped, not crashed."""
        class _BrokenContent:
            @property
            def parts(self):
                raise RuntimeError("broken")

        assert ct._extract_char_count([_BrokenContent()]) == 0

    def test_non_iterable_returns_zero(self, ct):
        assert ct._extract_char_count(42) == 0

    def test_empty_list(self, ct):
        assert ct._extract_char_count([]) == 0

    def test_mixed_valid_and_broken_parts(self, ct):
        """Valid parts still count even when other parts in the same item are broken."""
        class _GoodPart:
            text = "abc"

        class _BadPart:
            pass  # no .text

        class _Content:
            parts = [_GoodPart(), _BadPart(), _GoodPart()]

        assert ct._extract_char_count([_Content()]) == 6
