from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_submit_preflight import (
    HANDOFF_MISSING_DECISION,
    NO_CREATABLE_ORDER_DECISION,
    PAYLOAD_INVALID_DECISION,
    READY_DECISION,
    REJECT_DECISION,
    build_lsr_v2_third_trade_submit_preflight_report_from_files,
)
from trading_bot.core.lsr_v2_third_trade_handoff_dry_run import READY_DECISION as HANDOFF_READY_DECISION


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _handoff_report(*, ready: bool = True, unsafe: bool = False, payload_count: int = 1) -> dict:
    return {
        "status": "PASS" if ready else "WARN",
        "decision": HANDOFF_READY_DECISION if ready else "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_HANDOFF_PAYLOAD_INVALID",
        "cycle_id": "pc_third",
        "third_trade_eligible": True,
        "third_trade_rearm_ready": True,
        "third_trade_route_preflight_ready": ready,
        "third_trade_order_intent_ready": ready,
        "payload_valid_count": 1 if ready else 0,
        "payload_invalid_count": 0 if ready else 1,
        "would_create_paper_order_count": 1 if ready else 0,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called": unsafe,
        "broker_submit_called_by_third_trade_handoff": unsafe,
        "orders_submitted_by_third_trade_handoff": 0,
        "positions_opened_by_third_trade_handoff": 0,
        "positions_closed_by_third_trade_handoff": 0,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }


def _handoff_event(*, creatable: bool = True, invalid: bool = False, unsafe: bool = False) -> dict:
    payload = {
        "cycle_id": "pc_third",
        "symbol": "BTC/USDT" if not invalid else "",
        "timeframe": "5m",
        "candidate_id": "third_btc",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "side": "BUY",
        "order_type": "LIMIT",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "quantity": 2.5,
        "notional": 250.0,
        "max_positions": 1,
    }
    return {
        "event_type": "LSR_V2_THIRD_TRADE_HANDOFF_DRY_RUN",
        "cycle_id": "pc_third",
        "symbol": payload["symbol"],
        "timeframe": "5m",
        "candidate_id": "third_btc",
        "payload": payload,
        "payload_valid": not invalid,
        "payload_invalid_reasons": [] if not invalid else ["missing_symbol"],
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_amount": 2.5 if creatable and not invalid else 0.0,
        "position_size": 2.5 if creatable and not invalid else 0.0,
        "quantity": 2.5 if creatable and not invalid else 0.0,
        "notional": 250.0 if creatable and not invalid else 0.0,
        "max_positions": 1,
        "third_trade_order_intent_ready": True,
        "third_trade_route_preflight_ready": True,
        "would_create_paper_order": creatable,
        "would_create_order": creatable,
        "would_submit": unsafe,
        "would_submit_to_paper_broker": unsafe,
        "broker_submit_called": unsafe,
        "third_trade_submit_enabled": unsafe,
        "third_trade_execute_enabled": unsafe,
        "paper_order_submission_enabled": unsafe,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_third_trade_handoff": 0,
        "positions_opened_by_third_trade_handoff": 0,
        "positions_closed_by_third_trade_handoff": 0,
    }


def _seed(tmp_path: Path, *, ready: bool = True, creatable: bool = True, invalid: bool = False, unsafe: bool = False, rows: bool = True) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_third_trade_handoff_dry_run_report.json", _handoff_report(ready=ready, unsafe=unsafe, payload_count=1 if creatable else 0))
    if rows:
        _write_jsonl(data / "lsr_v2_third_trade_handoff_dry_run.jsonl", [_handoff_event(creatable=creatable, invalid=invalid, unsafe=unsafe)])
    return data


def test_handoff_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, ready=False)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == HANDOFF_MISSING_DECISION
    assert report["submit_preflight_events"] == 0
    assert report["orders_submitted_by_third_trade_submit_preflight"] == 0


def test_missing_handoff_event_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, rows=False)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == NO_CREATABLE_ORDER_DECISION
    assert "third_trade_handoff_event_missing" in report["blockers"]


def test_non_creatable_handoff_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, creatable=False)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == NO_CREATABLE_ORDER_DECISION
    assert report["would_prepare_submit_count"] == 0


def test_invalid_payload_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, invalid=True)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == PAYLOAD_INVALID_DECISION
    assert report["payload_invalid_count"] == 1


def test_submit_preflight_ready_but_no_submit(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == READY_DECISION
    assert report["status"] == "PASS"
    assert report["handoff_pass"] is True
    assert report["payload_valid_count"] == 1
    assert report["would_prepare_submit_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_third_trade_submit_preflight"] == 0
    assert report["positions_opened_by_third_trade_submit_preflight"] == 0
    assert report["paper_state_modified_by_third_trade_submit_preflight"] is False
    assert report["paper_status_modified_by_third_trade_submit_preflight"] is False
    assert (data / "lsr_v2_third_trade_submit_preflight_report.json").exists()
    assert (data / "lsr_v2_third_trade_submit_preflight.jsonl").exists()


def test_unsafe_handoff_rejected(tmp_path: Path) -> None:
    data = _seed(tmp_path, unsafe=True)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert report["orders_submitted_by_third_trade_submit_preflight"] == 0
    assert any("broker_submit" in b or "would_submit" in b for b in report["blockers"])


def test_strict_cycle_scope_uses_requested_cycle(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_preflight_report_from_files(data_dir=data, cycle_id="other_cycle")
    assert report["cycle_id"] == "other_cycle"
    assert report["decision"] == NO_CREATABLE_ORDER_DECISION
    assert report["submit_preflight_events"] == 0
