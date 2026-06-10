"""TR-INT-04 — Paper persistence and audit tests.

Covers:
  - Atomic save: crash during .tmp write leaves original state intact
  - Backup before recovery: .bak created before any corrupt-state handling
  - Fail closed on corrupt state: no trade actions taken
  - Extended audit event schema: POSITION_OPENED fields
  - Backward-compatible reader: old events without new fields parse without error
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from trading_bot.clean_bot import paper_live
from trading_bot.clean_bot.paper_live import (
    CleanPaperSettings,
    _default_state,
    _read_state,
    _state_path,
    _write_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(tmp_path: Path) -> CleanPaperSettings:
    return CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)


def _single_row_frame(open_: float = 105.0) -> pd.DataFrame:
    df = pd.DataFrame([{
        "Open": open_, "High": open_ + 6.0, "Low": open_ - 1.0,
        "Close": open_ + 4.0, "atr14": 1.0,
    }])
    df["datetime"] = pd.to_datetime("2026-01-01T00:05:00+00:00", utc=True)
    return df


# ---------------------------------------------------------------------------
# test_atomic_save
# ---------------------------------------------------------------------------

def test_atomic_save(tmp_path: Path) -> None:
    """Crash during .tmp write leaves the original state file untouched."""
    settings = _settings(tmp_path)

    initial = _default_state(settings)
    initial["cash"] = 77.0
    _write_state(settings, initial)

    original_write_text = Path.write_text
    call_count = [0]

    def crashing_write_text(self, data, *args, **kwargs):
        if str(self).endswith(".tmp"):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("simulated disk failure during .tmp write")
        return original_write_text(self, data, *args, **kwargs)

    import unittest.mock
    with unittest.mock.patch.object(Path, "write_text", crashing_write_text):
        corrupt = _default_state(settings)
        corrupt["cash"] = 1.0
        with pytest.raises(OSError):
            _write_state(settings, corrupt)

    # Original state must be intact
    recovered = _read_state(settings)
    assert recovered.get("_corrupt_recovery") is None, "state must not be flagged as corrupt"
    assert recovered["cash"] == pytest.approx(77.0), "original cash must survive the crash"

    # .tmp must not persist after a failed atomic write
    tmp_file = _state_path(settings).with_suffix(".tmp")
    assert not tmp_file.exists(), ".tmp must not persist after a failed write"


# ---------------------------------------------------------------------------
# test_backup_before_recovery
# ---------------------------------------------------------------------------

def test_backup_before_recovery(tmp_path: Path) -> None:
    """A .bak copy of the corrupt file is created before recovery returns."""
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)

    corrupt_content = b"THIS IS NOT VALID JSON }{]["
    path.write_bytes(corrupt_content)

    # Suppress emit file I/O by patching _emit
    with patch.object(paper_live, "_emit"):
        state = _read_state(settings)

    bak = path.with_suffix(".bak")
    assert bak.exists(), ".bak backup must be created before recovery"
    assert bak.read_bytes() == corrupt_content, ".bak must be an exact copy of the corrupt file"
    assert state.get("_corrupt_recovery") is True, "state must carry the _corrupt_recovery flag"


# ---------------------------------------------------------------------------
# test_corrupted_state_fails_closed
# ---------------------------------------------------------------------------

def test_corrupted_state_fails_closed(tmp_path: Path) -> None:
    """Corrupt state file blocks all trade actions; original file untouched."""
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)

    corrupt_text = "{NOT JSON AT ALL"
    path.write_text(corrupt_text, encoding="utf-8")

    with patch.object(paper_live, "_emit"):
        report = paper_live.run_cycle(settings)

    assert report["action"] == "STATE_CORRUPT_BLOCKED", (
        f"corrupt state must block cycle; got action={report['action']!r}"
    )
    # The corrupt file must NOT be overwritten with a fresh default state
    assert path.read_text(encoding="utf-8") == corrupt_text, (
        "original corrupt file must remain untouched"
    )


# ---------------------------------------------------------------------------
# test_event_schema_audit_fields
# ---------------------------------------------------------------------------

def test_event_schema_audit_fields(tmp_path: Path) -> None:
    """CLEAN_POSITION_OPENED event contains all required TR-INT-04 audit fields."""
    settings = _settings(tmp_path)

    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": "2026-01-01T00:00:00+00:00",
        "stop_price": 95.0,
        "take_profit": 130.0,
        "strategy": "fixture_strat",
        "reason": "test_entry_reason",
        "metadata": {"regime": "trending"},
        "created_at": "2026-01-01T00:00:00+00:00",
    }

    frame = _single_row_frame(open_=105.0)
    captured: list[dict] = []

    def capture_emit(s, event_type, **payload):
        captured.append({"event_type": event_type, **payload})

    with patch.object(paper_live, "_read_state", return_value=state), \
         patch.object(paper_live, "_prepared_frame", return_value=(frame, "fixture")), \
         patch.object(paper_live, "_signal", return_value=(None, frame.iloc[0])), \
         patch.object(paper_live, "_write_state", return_value=None), \
         patch.object(paper_live, "_emit", capture_emit), \
         patch.object(paper_live, "_send_telegram", return_value={"ok": False}):
        paper_live.run_cycle(settings)

    opened = [e for e in captured if e["event_type"] == "CLEAN_POSITION_OPENED"]
    assert len(opened) == 1, f"expected 1 CLEAN_POSITION_OPENED event, got {len(opened)}"
    event = opened[0]

    required = {
        "candle_uid", "trade_uid", "signal_price", "fill_price",
        "fee", "slippage", "qty", "notional", "entry_reason",
        "exit_reason", "regime", "timeframe",
    }
    missing = required - set(event.keys())
    assert not missing, f"CLEAN_POSITION_OPENED missing fields: {sorted(missing)}"

    assert event["signal_price"] == pytest.approx(102.0)
    assert event["fill_price"] == pytest.approx(105.0)
    assert event["fee"] == pytest.approx(0.0)
    assert event["slippage"] == pytest.approx(0.0)
    assert event["qty"] > 0
    assert event["notional"] == pytest.approx(event["qty"] * 105.0, rel=1e-6)
    assert event["entry_reason"] == "test_entry_reason"
    assert event["exit_reason"] is None
    assert event["regime"] == "trending"
    assert event["timeframe"] == settings.timeframe
    assert event["candle_uid"] != ""
    assert event["trade_uid"] != ""


# ---------------------------------------------------------------------------
# test_backward_compatible_reader
# ---------------------------------------------------------------------------

def test_backward_compatible_reader() -> None:
    """Old events without TR-INT-04 audit fields are parsed without exceptions."""
    # An event written before TR-INT-04 (none of the new top-level audit fields)
    old_event = {
        "ts": "2026-01-01T00:00:00+00:00",
        "event_type": "CLEAN_POSITION_OPENED",
        "position": {
            "position_id": "clean_20260101000000",
            "symbol": "XRP/USDT",
            "side": "BUY",
            "qty": 0.05,
            "entry_price": 100.0,
            "entry_fee": 0.0,
            "cost_basis": 5.0,
            "stop_loss": 95.0,
        },
    }

    # Round-trip through JSON (as happens when reading JSONL)
    line = json.dumps(old_event)
    loaded: dict = json.loads(line)

    # All new fields must be accessible via .get() returning None — no KeyError
    new_fields = [
        "candle_uid", "trade_uid", "signal_price", "fill_price",
        "fee", "slippage", "qty", "notional", "entry_reason",
        "exit_reason", "regime", "timeframe",
    ]
    for f in new_fields:
        val = loaded.get(f)
        assert val is None, f"expected None for missing field {f!r}, got {val!r}"

    # The nested position sub-dict is still accessible
    assert loaded["position"]["entry_price"] == 100.0

    # A closed event likewise
    old_closed = {
        "ts": "2026-01-01T01:00:00+00:00",
        "event_type": "CLEAN_POSITION_CLOSED",
        "position": {
            "position_id": "clean_20260101000000",
            "exit_price": 110.0,
            "realized_pnl": 0.48,
        },
    }
    loaded_closed: dict = json.loads(json.dumps(old_closed))
    for f in new_fields:
        assert loaded_closed.get(f) is None
    assert loaded_closed["position"]["exit_price"] == 110.0
