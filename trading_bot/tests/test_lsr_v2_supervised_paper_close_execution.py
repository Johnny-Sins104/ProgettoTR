from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_supervised_paper_close_execution import (
    CLOSED_DECISION,
    NOT_ENABLED_DECISION,
    CONFIRMATION_MISSING_DECISION,
    POSITION_NOT_FOUND_DECISION,
    STATE_INCONSISTENT_DECISION,
    build_lsr_v2_supervised_paper_close_execution_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_ready(tmp_path: Path, *, with_position: bool = True, status_open_positions: int = 1) -> Path:
    data = tmp_path / "data"
    event = {
        "event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT",
        "cycle_id": "pc_close",
        "position_id": "pos_1",
        "order_id": "ord_1",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "current_status": "OPEN",
        "position_found": True,
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 112.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "position_size": 2.0,
        "notional": 200.0,
        "risk_amount": 10.0,
        "close_required_diagnostic": True,
        "take_profit_hit_diagnostic": True,
        "stop_hit_diagnostic": False,
        "close_reason": "TAKE_PROFIT_HIT_DIAGNOSTIC",
        "would_prepare_close": True,
        "would_close_position": False,
        "broker_close_called": False,
    }
    _write_jsonl(data / "lsr_v2_supervised_paper_close_preflight.jsonl", [event])
    _write_json(data / "lsr_v2_supervised_paper_close_preflight_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT_READY",
        "cycle_id": "pc_close",
        "close_required_diagnostic_count": 1,
        "would_prepare_close_count": 1,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "total_notional": 200.0,
        "total_risk_amount": 10.0,
    })
    positions = {}
    if with_position:
        positions = {
            "pos_1": {
                "position_id": "pos_1",
                "order_id": "ord_1",
                "cycle_id": "pc_close",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": "OPEN",
                "open": True,
                "source": "lsr_v2_supervised_paper_submit_execution",
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "position_size": 2.0,
                "notional": 200.0,
                "risk_amount": 10.0,
                "unrealized_pnl": 24.0,
            }
        }
    _write_json(data / "paper_state.json", {
        "balance": 1000.0,
        "realized_pnl": 0.0,
        "orders": {},
        "positions": positions,
    })
    _write_json(data / "paper_status.json", {
        "open_positions": status_open_positions,
        "pending_orders": 0,
        "balance": 1000.0,
        "realized_pnl": 0.0,
        "position_monitor": {"open_position_count": status_open_positions, "positions": []},
    })
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_close"}])
    return data


def test_default_not_enabled_does_not_mutate(tmp_path: Path) -> None:
    data = _seed_ready(tmp_path)
    before = json.loads((data / "paper_state.json").read_text())
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    after = json.loads((data / "paper_state.json").read_text())
    assert report["decision"] == NOT_ENABLED_DECISION
    assert report["positions_closed_by_lsr_v2_close_execution"] == 0
    assert report["broker_close_called"] is False
    assert before == after


def test_enabled_without_confirmation_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed_ready(tmp_path)
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_ENABLE", "1")
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["positions_closed_by_lsr_v2_close_execution"] == 0


def test_confirmed_close_marks_position_closed_and_updates_status(tmp_path: Path, monkeypatch) -> None:
    data = _seed_ready(tmp_path)
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_CONFIRMATION", "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_MAX_POSITIONS", "1")
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == CLOSED_DECISION
    assert report["positions_closed_by_lsr_v2_close_execution"] == 1
    assert report["broker_close_called"] is True
    assert report["orders_submitted_by_lsr_v2_close_execution"] == 0
    assert report["positions_opened_by_lsr_v2_close_execution"] == 0
    assert report["open_lsr_v2_positions_after"] == 0
    assert report["paper_status_open_positions_after"] == 0
    assert report["backup_state_path"]
    assert report["backup_status_path"]
    state = json.loads((data / "paper_state.json").read_text())
    pos = state["positions"]["pos_1"]
    assert pos["status"] == "CLOSED"
    assert pos["open"] is False
    assert pos["close_reason"] == "TAKE_PROFIT_HIT_DIAGNOSTIC"
    assert pos["realized_pnl"] == 24.0
    status = json.loads((data / "paper_status.json").read_text())
    assert status["open_positions"] == 0
    rows = [json.loads(line) for line in (data / "lsr_v2_supervised_paper_close_execution.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event_type"] == "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION"


def test_position_not_found_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed_ready(tmp_path, with_position=False, status_open_positions=0)
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_CONFIRMATION", "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY")
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["positions_closed_by_lsr_v2_close_execution"] == 0


def test_status_inconsistent_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed_ready(tmp_path, status_open_positions=0)
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_CONFIRMATION", "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY")
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert report["positions_closed_by_lsr_v2_close_execution"] == 0


def test_max_position_cap_blocks_duplicates(tmp_path: Path, monkeypatch) -> None:
    data = _seed_ready(tmp_path)
    state = json.loads((data / "paper_state.json").read_text())
    state["positions"]["pos_2"] = dict(state["positions"]["pos_1"], position_id="pos_2")
    _write_json(data / "paper_state.json", state)
    _write_json(data / "paper_status.json", {"open_positions": 2, "pending_orders": 0})
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_CONFIRMATION", "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_MAX_POSITIONS", "1")
    report = build_lsr_v2_supervised_paper_close_execution_report_from_files(data_dir=data)
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_MAX_POSITION_CAP_BLOCKED"
    assert report["positions_closed_by_lsr_v2_close_execution"] == 0
