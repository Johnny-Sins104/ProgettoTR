from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.paper_legacy_position_quarantine import (
    EVENT_STATE_RESET,
    LegacyPositionQuarantineSettings,
    quarantine_legacy_positions,
    reset_legacy_paper_state,
    write_legacy_position_quarantine_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _legacy_state() -> dict:
    return {
        "initial_balance": 1000.0,
        "balance": 996.35,
        "realized_pnl": -3.65,
        "peak_balance": 1000.0,
        "orders": {
            "po_1": {
                "order_id": "po_1",
                "symbol": "ETH/USDT",
                "side": "SELL",
                "status": "FILLED",
                "metadata": {"cycle_id": "pc_1", "combination": "ScoreOnly+Meta_OK(p:66.6%,q:71.2)", "paper_unlock": False, "unlock_profile": None},
            }
        },
        "positions": {
            "pp_1": {
                "position_id": "pp_1",
                "symbol": "ETH/USDT",
                "side": "SELL",
                "entry_price": 2104.61,
                "qty": 0.47,
                "status": "OPEN",
                "realized_pnl": 0.0,
                "metadata": {"cycle_id": "pc_1", "combination": "ScoreOnly+Meta_OK(p:66.6%,q:71.2)", "paper_unlock": False, "unlock_profile": None, "source_order_id": "po_1"},
            },
            "pp_closed": {
                "position_id": "pp_closed",
                "symbol": "BTC/USDT",
                "side": "SELL",
                "entry_price": 76596.0,
                "qty": 0.013,
                "status": "CLOSED",
                "realized_pnl": -2.45,
                "metadata": {"cycle_id": "pc_0", "combination": "ScoreOnly+Meta_OK(p:89.4%,q:81.7)", "paper_unlock": False, "unlock_profile": None, "source_order_id": "po_0"},
            },
        },
    }


def test_report_detects_legacy_open_positions() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_json(base / "paper_state.json", _legacy_state())
        _write_json(base / "paper_status.json", {"open_positions": 1, "positions": [{"symbol": "ETH/USDT", "unrealized_pnl": 3.0}]})
        report = write_legacy_position_quarantine_report(base, LegacyPositionQuarantineSettings())
        assert report["status"] == "WARN"
        assert report["decision"]["legacy_open_positions_count"] == 1
        assert report["legacy_summary"]["legacy_orders_count"] == 1
        assert "ETH/USDT" in report["legacy_summary"]["affected_symbols"]


def test_quarantine_marks_metadata_without_closing() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_json(base / "paper_state.json", _legacy_state())
        _write_json(base / "paper_status.json", {"open_positions": 1})
        report = quarantine_legacy_positions(base, LegacyPositionQuarantineSettings())
        state = json.loads((base / "paper_state.json").read_text(encoding="utf-8"))
        assert report["decision"]["quarantine_applied"] is True
        assert state["positions"]["pp_1"]["status"] == "OPEN"
        assert state["positions"]["pp_1"]["metadata"]["legacy_quarantined"] is True
        assert (base / "paper_legacy_quarantine_backups").exists()


def test_reset_requires_confirmation() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_json(base / "paper_state.json", _legacy_state())
        try:
            reset_legacy_paper_state(base, LegacyPositionQuarantineSettings())
        except ValueError:
            pass
        else:
            raise AssertionError("reset must require confirmation")


def test_reset_cleans_state_and_rotates_events() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_json(base / "paper_state.json", _legacy_state())
        _write_json(base / "paper_status.json", {"open_positions": 1, "positions": [{"symbol": "ETH/USDT", "unrealized_pnl": 3.0}]})
        (base / "paper_events.jsonl").write_text('{"event_type":"PAPER_ORDER_SUBMITTED"}\n', encoding="utf-8")
        report = reset_legacy_paper_state(base, LegacyPositionQuarantineSettings(), confirm_reset=True)
        state = json.loads((base / "paper_state.json").read_text(encoding="utf-8"))
        status = json.loads((base / "paper_status.json").read_text(encoding="utf-8"))
        events = (base / "paper_events.jsonl").read_text(encoding="utf-8")
        assert report["status"] == "PASS"
        assert report["decision"]["reset_applied"] is True
        assert state["orders"] == {}
        assert state["positions"] == {}
        assert status["open_positions"] == 0
        assert EVENT_STATE_RESET in events
        assert "PAPER_ORDER_SUBMITTED" not in events


if __name__ == "__main__":
    test_report_detects_legacy_open_positions()
    test_quarantine_marks_metadata_without_closing()
    test_reset_requires_confirmation()
    test_reset_cleans_state_and_rotates_events()
    print("Paper legacy position quarantine tests passed.")
