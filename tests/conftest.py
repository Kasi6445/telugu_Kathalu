"""tests/conftest.py — shared fixtures for cost_tracker tests."""
import pytest
import lib.cost_tracker as _ct


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """
    Applied automatically to every test:
      - Redirect all JSONL writes to tmp_path (never touches logs/cost_audit.jsonl).
      - Zero out session totals and reset stage context so tests are fully isolated.
    """
    monkeypatch.setattr(_ct, "_logs_dir", lambda: tmp_path)
    with _ct._session_lock:
        _ct._session_total = 0.0
        _ct._tts_session_total = 0.0
    _ct._stage_ctx.current = "unknown"
    yield
    with _ct._session_lock:
        _ct._session_total = 0.0
        _ct._tts_session_total = 0.0


@pytest.fixture()
def ct():
    """The cost_tracker module — state already reset by _reset_state."""
    import lib.cost_tracker
    return lib.cost_tracker


@pytest.fixture()
def log_path(tmp_path):
    """Path to the JSONL file that all test log writes land in."""
    return tmp_path / "cost_audit.jsonl"
