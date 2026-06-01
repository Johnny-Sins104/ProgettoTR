from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_paper_status_reconciliation import (  # type: ignore
    READY_DECISION,
    SYNC_AVAILABLE_DECISION,
    SYNC_APPLIED_DECISION,
    OUT_OF_SYNC_DECISION,
    REJECT_DECISION,
    SYNC_ENABLE_ENV,
    SYNC_CONFIRMATION_ENV,
    SYNC_CONFIRMATION_PHRASE,
    build_lsr_v2_paper_status_reconciliation_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _state(open_positions: int = 1) -> dict:
    positions = {}
    if open_positions:
        positions["pos_1"] = {
            "position_id": "pos_1",
            "order_id": "ord_1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "entry_price": 100.0,
            "current_price": 103.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "position_size": 0.5,
            "notional": 50.0,
            "risk_amount": 2.5,
            "risk_per_trade_pct": 0.0025,
            "status": "OPEN",
            "open": True,
            "metadata": {
                "cycle_id": "pc_test",
                "paper_order_source": "lsr_v2_supervised_paper_submit_execution",
            },
        }
    return {
        "balance": 1000.0,
        "orders": {},
        "positions": positions,
        "realized_pnl": 0.0,
    }


def _status(open_positions: int = 0) -> dict:
    return {
        "balance": 1000.0,
        "equity": 1000.0,
        "open_positions": open_positions,
        "pending_orders": 0,
        "positions": [] if open_positions == 0 else [{"symbol": "BTC/USDT"}],
        "position_monitor": {
            "status": "FLAT" if open_positions == 0 else "OPEN",
            "open_position_count": open_positions,
            "positions": [] if open_positions == 0 else [{"symbol": "BTC/USDT"}],
            "account": {"open_positions": open_positions, "pending_orders": 0, "raw": {"open_positions": open_positions, "pending_orders": 0, "positions": []}},
        },
    }


def test_audit_detects_status_out_of_sync_without_mutation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_json(data_dir / "paper_state.json", _state(open_positions=1))
    _write_json(data_dir / "paper_status.json", _status(open_positions=0))
    before = (data_dir / "paper_status.json").read_text(encoding="utf-8")

    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=data_dir, cycle_id="pc_test")

    assert report["decision"] == SYNC_AVAILABLE_DECISION
    assert report["paper_status_modified"] is False
    assert report["state_open_positions"] == 1
    assert report["status_open_positions_before"] == 0
    assert (data_dir / "paper_status.json").read_text(encoding="utf-8") == before
    assert report["orders_submitted_by_status_reconciliation"] == 0
    assert report["positions_opened_by_status_reconciliation"] == 0


def test_sync_applies_status_update_with_backup(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    _write_json(data_dir / "paper_state.json", _state(open_positions=1))
    _write_json(data_dir / "paper_status.json", _status(open_positions=0))
    monkeypatch.setenv(SYNC_ENABLE_ENV, "1")
    monkeypatch.setenv(SYNC_CONFIRMATION_ENV, SYNC_CONFIRMATION_PHRASE)

    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=data_dir, cycle_id="pc_test")

    assert report["decision"] == SYNC_APPLIED_DECISION
    assert report["paper_status_modified"] is True
    assert report["status_open_positions_after"] == 1
    assert report["position_monitor_open_positions_after"] == 1
    assert report["sync_required_after"] is False
    assert report["backup_path"]
    assert Path(report["backup_path"]).exists()
    status = json.loads((data_dir / "paper_status.json").read_text(encoding="utf-8"))
    assert status["open_positions"] == 1
    assert status["position_monitor"]["open_position_count"] == 1
    assert status["lsr_v2_status_reconciliation"]["status"] == "SYNCED_FROM_PAPER_STATE"


def test_consistent_status_is_ready(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_json(data_dir / "paper_state.json", _state(open_positions=1))
    _write_json(data_dir / "paper_status.json", _status(open_positions=1))

    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=data_dir, cycle_id="pc_test")

    assert report["decision"] == READY_DECISION
    assert report["status"] == "PASS"
    assert report["paper_status_modified"] is False


def test_sync_enabled_without_confirmation_does_not_modify(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    _write_json(data_dir / "paper_state.json", _state(open_positions=1))
    _write_json(data_dir / "paper_status.json", _status(open_positions=0))
    monkeypatch.setenv(SYNC_ENABLE_ENV, "1")
    monkeypatch.setenv(SYNC_CONFIRMATION_ENV, "WRONG")

    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=data_dir, cycle_id="pc_test")

    assert report["decision"] == OUT_OF_SYNC_DECISION
    assert report["paper_status_modified"] is False
    assert "sync_confirmation_missing" in report["blockers"]


def test_rejects_duplicate_lsr_positions(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    state = _state(open_positions=1)
    state["positions"]["pos_2"] = {**state["positions"]["pos_1"], "position_id": "pos_2", "order_id": "ord_2"}
    _write_json(data_dir / "paper_state.json", state)
    _write_json(data_dir / "paper_status.json", _status(open_positions=2))

    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=data_dir, cycle_id="pc_test")

    assert report["decision"] == REJECT_DECISION
    assert report["duplicate_position_check"] is False
    assert report["max_positions_check"] is False
