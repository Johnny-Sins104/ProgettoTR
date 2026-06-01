from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_supervised_paper_close_preflight import (
    EVENT_TYPE,
    READY_DECISION,
    CLOSE_NOT_REQUIRED_DECISION,
    POSITION_NOT_FOUND_DECISION,
    STATE_INCONSISTENT_DECISION,
    build_lsr_v2_supervised_paper_close_preflight_event,
    build_lsr_v2_supervised_paper_close_preflight_report_from_files,
    close_preflight_env_state,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_close_required(tmp_path: Path, *, close_required: bool = True, status_open_positions: int = 1, with_position: bool = True) -> Path:
    data = tmp_path / "data"
    monitor = {
        "event_type": "LSR_V2_OPEN_POSITION_MONITOR_AUDIT",
        "cycle_id": "pc_test",
        "position_id": "pos_1",
        "order_id": "ord_1",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "current_status": "OPEN",
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 112.0 if close_required else 104.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "position_size": 2.0,
        "notional": 200.0,
        "risk_amount": 10.0,
        "unrealized_pnl": 24.0 if close_required else 8.0,
        "risk_multiple_current": 2.4 if close_required else 0.8,
        "stop_hit_diagnostic": False,
        "take_profit_hit_diagnostic": close_required,
        "close_required_diagnostic": close_required,
        "paper_state_consistency": True,
        "paper_status_consistency": True,
    }
    _write_jsonl(data / "lsr_v2_open_position_monitor.jsonl", [monitor])
    _write_json(data / "lsr_v2_open_position_monitor_report.json", {
        "status": "WARN" if close_required else "PASS",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_REQUIRED_DIAGNOSTIC" if close_required else "LSR_V2_OPEN_POSITION_MONITOR_READY",
        "cycle_id": "pc_test",
        "monitor_events": 1,
        "open_lsr_v2_position_count": 1,
        "paper_state_consistency": True,
        "paper_status_consistency": True,
        "close_required_diagnostic": close_required,
        "take_profit_hit_diagnostic_count": 1 if close_required else 0,
        "stop_hit_diagnostic_count": 0,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
    })
    _write_json(data / "lsr_v2_paper_position_lifecycle_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_PAPER_POSITION_LIFECYCLE_READY",
        "cycle_id": "pc_test",
        "paper_state_consistency": True,
        "paper_status_consistency": True,
        "open_lsr_v2_position_count": 1,
    })
    positions = {}
    if with_position:
        positions = {
            "pos_1": {
                "position_id": "pos_1",
                "order_id": "ord_1",
                "cycle_id": "pc_test",
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
            }
        }
    _write_json(data / "paper_state.json", {"orders": {}, "positions": positions})
    _write_json(data / "paper_status.json", {"open_positions": status_open_positions, "pending_orders": 0})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test"}])
    return data


def test_close_preflight_event_never_closes() -> None:
    event = build_lsr_v2_supervised_paper_close_preflight_event(
        monitor_event={
            "cycle_id": "pc",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "close_required_diagnostic": True,
            "take_profit_hit_diagnostic": True,
        },
        position={"position_id": "p1", "symbol": "BTC/USDT", "side": "BUY", "status": "OPEN", "open": True},
        env_state={"close_enabled": True, "close_confirmation_ok": True},
    )
    assert event["event_type"] == EVENT_TYPE
    assert event["would_prepare_close"] is True
    assert event["would_close_position"] is False
    assert event["broker_close_called"] is False
    assert event["automatic_close_enabled"] is False


def test_report_ready_when_tp_close_required(tmp_path: Path) -> None:
    data = _seed_close_required(tmp_path, close_required=True)
    report = build_lsr_v2_supervised_paper_close_preflight_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["close_required_diagnostic_count"] == 1
    assert report["take_profit_hit_diagnostic_count"] == 1
    assert report["would_prepare_close_count"] == 1
    assert report["would_close_position_count"] == 0
    assert report["broker_close_called"] is False
    rows = [json.loads(line) for line in (data / "lsr_v2_supervised_paper_close_preflight.jsonl").read_text().splitlines()]
    assert rows[0]["close_reason"] == "TAKE_PROFIT_HIT_DIAGNOSTIC"


def test_report_close_not_required(tmp_path: Path) -> None:
    data = _seed_close_required(tmp_path, close_required=False)
    report = build_lsr_v2_supervised_paper_close_preflight_report_from_files(data_dir=data)
    assert report["decision"] == CLOSE_NOT_REQUIRED_DECISION
    assert report["would_prepare_close_count"] == 0
    assert report["would_close_position_count"] == 0


def test_report_position_not_found(tmp_path: Path) -> None:
    data = _seed_close_required(tmp_path, close_required=True, status_open_positions=0, with_position=False)
    report = build_lsr_v2_supervised_paper_close_preflight_report_from_files(data_dir=data)
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert "matching_position_not_found" in report["blockers"]
    assert report["orders_submitted_by_close_preflight"] == 0


def test_report_state_inconsistent_when_status_mismatch(tmp_path: Path) -> None:
    data = _seed_close_required(tmp_path, close_required=True, status_open_positions=0, with_position=True)
    report = build_lsr_v2_supervised_paper_close_preflight_report_from_files(data_dir=data)
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert "paper_status_inconsistent" in report["blockers"]


def test_env_state_requires_exact_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_PREFLIGHT_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_CLOSE_PREFLIGHT_CONFIRMATION", "wrong")
    state = close_preflight_env_state()
    assert state["close_enabled"] is True
    assert state["close_confirmation_ok"] is False
