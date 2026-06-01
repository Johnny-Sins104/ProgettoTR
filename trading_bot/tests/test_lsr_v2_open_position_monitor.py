from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_open_position_monitor import (
    build_lsr_v2_open_position_monitor_event,
    build_lsr_v2_open_position_monitor_report_from_files,
    latest_market_snapshot,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_open_position(tmp_path: Path, *, current_price: float = 101.0) -> None:
    data = tmp_path
    _write_json(data / "lsr_v2_supervised_paper_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": "pc_test",
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_submit_execution.jsonl", [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "candidate_id": "c1",
        "order_id": "o1",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "position_size": 2.0,
        "notional": 200.0,
        "risk_amount": 10.0,
        "orders_submitted_by_lsr_v2_submit": 1,
        "positions_opened_by_lsr_v2_submit": 1,
    }])
    _write_json(data / "paper_state.json", {
        "orders": {
            "o1": {
                "order_id": "o1",
                "cycle_id": "pc_test",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": "FILLED",
                "source": "lsr_v2_supervised_paper_submit_execution",
            }
        },
        "positions": {
            "p1": {
                "position_id": "p1",
                "order_id": "o1",
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
                "opened_at": "2026-05-28T19:00:00+00:00",
            }
        },
    })
    _write_json(data / "paper_status.json", {"open_positions": 1, "pending_orders": 0})
    _write_jsonl(data / "paper_events.jsonl", [
        {"event_type": "CYCLE_STARTED", "cycle_id": "pc_test", "timeframe": "5m", "ts": "2026-05-28T19:05:00+00:00"},
        {"event_type": "ASSET_SCANNED", "cycle_id": "pc_test", "symbol": "BTC/USDT", "last_price": current_price, "timeframe": "5m", "ts": "2026-05-28T19:10:00+00:00"},
    ])


def test_latest_market_snapshot_selects_latest_price() -> None:
    rows = [
        {"event_type": "ASSET_SCANNED", "symbol": "BTC/USDT", "last_price": 100, "ts": "t1"},
        {"event_type": "ASSET_SCANNED", "symbol": "ETH/USDT", "last_price": 50, "ts": "t2"},
        {"event_type": "ASSET_SCANNED", "symbol": "BTC/USDT", "last_price": 101, "ts": "t3"},
    ]
    snap = latest_market_snapshot(paper_events=rows, symbol="BTC/USDT")
    assert snap["current_price"] == 101
    assert snap["current_price_ts"] == "t3"


def test_monitor_event_computes_pnl_r_and_sl_tp_distance() -> None:
    event = build_lsr_v2_open_position_monitor_event(
        lifecycle_event={"cycle_id": "pc", "symbol": "BTC/USDT", "side": "BUY", "position_id": "p1", "entry_price": 100, "risk_amount": 10},
        position={"position_id": "p1", "symbol": "BTC/USDT", "side": "BUY", "status": "OPEN", "entry_price": 100, "stop_loss": 95, "take_profit": 110, "position_size": 2, "risk_amount": 10},
        market_snapshot={"current_price": 103, "timeframe": "5m"},
    )
    assert event["unrealized_pnl"] == 6
    assert event["risk_multiple_current"] == 0.6
    assert event["distance_to_stop"] == 8
    assert event["distance_to_take_profit"] == 7
    assert event["close_required_diagnostic"] is False
    assert event["orders_submitted_by_open_position_monitor"] == 0


def test_report_ready_for_open_position(tmp_path: Path) -> None:
    _seed_open_position(tmp_path, current_price=101.0)
    report = build_lsr_v2_open_position_monitor_report_from_files(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_OPEN_POSITION_MONITOR_READY"
    assert report["open_lsr_v2_position_count"] == 1
    assert report["paper_status_consistency"] is True
    assert report["unrealized_pnl_total"] == 2.0
    assert report["risk_multiple_current_avg"] == 0.2
    assert report["broker_submit_called_by_open_position_monitor"] is False


def test_report_warns_when_stop_hit(tmp_path: Path) -> None:
    _seed_open_position(tmp_path, current_price=94.0)
    report = build_lsr_v2_open_position_monitor_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_REQUIRED_DIAGNOSTIC"
    assert report["stop_hit_diagnostic_count"] == 1
    assert report["close_required_diagnostic"] is True
    assert report["automatic_close_enabled"] is False


def test_report_warns_on_status_mismatch(tmp_path: Path) -> None:
    _seed_open_position(tmp_path, current_price=101.0)
    _write_json(tmp_path / "paper_status.json", {"open_positions": 0, "pending_orders": 0})
    report = build_lsr_v2_open_position_monitor_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_MONITOR_STATE_INCONSISTENT"
    assert "paper_status_inconsistent" in report["blockers"]
