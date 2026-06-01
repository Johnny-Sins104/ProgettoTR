from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_submit_boundary import (
    CONFIRMATION_MISSING_DECISION,
    MAX_ORDER_CAP_DECISION,
    NOT_ARMED_DECISION,
    PAYLOAD_INVALID_DECISION,
    PREFLIGHT_MISSING_DECISION,
    READY_ARMED_DECISION,
    REJECT_DECISION,
    LSRV2ThirdTradeSubmitBoundarySettings,
    build_lsr_v2_third_trade_submit_boundary_report_from_files,
)
from trading_bot.core.lsr_v2_third_trade_submit_preflight import READY_DECISION as PREFLIGHT_READY_DECISION


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _preflight_report(*, ready: bool = True, unsafe: bool = False) -> dict:
    return {
        "status": "PASS" if ready else "WARN",
        "decision": PREFLIGHT_READY_DECISION if ready else "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_PAYLOAD_INVALID",
        "cycle_id": "pc_third",
        "third_trade_eligible": True,
        "third_trade_rearm_ready": True,
        "third_trade_route_preflight_ready": ready,
        "third_trade_order_intent_ready": ready,
        "third_trade_handoff_ready": ready,
        "payload_valid_count": 1 if ready else 0,
        "payload_invalid_count": 0 if ready else 1,
        "would_create_paper_order_count": 1 if ready else 0,
        "would_prepare_submit_count": 1 if ready else 0,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called": unsafe,
        "broker_submit_called_by_third_trade_submit_preflight": unsafe,
        "orders_submitted_by_third_trade_submit_preflight": 0,
        "positions_opened_by_third_trade_submit_preflight": 0,
        "positions_closed_by_third_trade_submit_preflight": 0,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }


def _preflight_event(*, prepared: bool = True, invalid: bool = False, unsafe: bool = False) -> dict:
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
        "event_type": "LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT",
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
        "risk_amount": 2.5 if prepared and not invalid else 0.0,
        "position_size": 2.5 if prepared and not invalid else 0.0,
        "quantity": 2.5 if prepared and not invalid else 0.0,
        "notional": 250.0 if prepared and not invalid else 0.0,
        "max_positions": 1,
        "third_trade_order_intent_ready": True,
        "third_trade_route_preflight_ready": True,
        "third_trade_handoff_ready": True,
        "would_create_paper_order": prepared,
        "would_create_order": prepared,
        "would_prepare_submit": prepared,
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
        "orders_submitted_by_third_trade_submit_preflight": 0,
        "positions_opened_by_third_trade_submit_preflight": 0,
        "positions_closed_by_third_trade_submit_preflight": 0,
    }


def _seed(tmp_path: Path, *, ready: bool = True, prepared: bool = True, invalid: bool = False, unsafe: bool = False, rows: bool = True) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_third_trade_submit_preflight_report.json", _preflight_report(ready=ready, unsafe=unsafe))
    if rows:
        _write_jsonl(data / "lsr_v2_third_trade_submit_preflight.jsonl", [_preflight_event(prepared=prepared, invalid=invalid, unsafe=unsafe)])
    return data


def _settings(**kwargs) -> LSRV2ThirdTradeSubmitBoundarySettings:
    base = {
        "submit_arm": "",
        "submit_confirmation": "",
        "max_orders": 1,
        "mode": "paper",
    }
    base.update(kwargs)
    return LSRV2ThirdTradeSubmitBoundarySettings(**base)


def test_not_armed_is_warn_and_non_mutating(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(data_dir=data, settings=_settings())
    assert report["decision"] == NOT_ARMED_DECISION
    assert report["status"] == "WARN"
    assert report["third_trade_submit_ready_count"] == 0
    assert report["orders_submitted_by_third_trade_submit_boundary"] == 0
    assert report["positions_opened_by_third_trade_submit_boundary"] == 0
    assert report["paper_state_modified_by_third_trade_submit_boundary"] is False
    assert (data / "lsr_v2_third_trade_submit_boundary_report.json").exists()


def test_confirmation_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="wrong"),
    )
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["third_trade_submit_armed"] is True
    assert report["third_trade_submit_confirmation_ok"] is False
    assert report["would_submit_count"] == 0


def test_submit_boundary_ready_armed_but_no_submit(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"),
    )
    assert report["decision"] == READY_ARMED_DECISION
    assert report["status"] == "PASS"
    assert report["submit_preflight_pass"] is True
    assert report["third_trade_submit_ready_count"] == 1
    assert report["would_create_order_count"] == 1
    assert report["would_prepare_submit_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_third_trade_submit_boundary"] == 0
    assert report["positions_opened_by_third_trade_submit_boundary"] == 0
    assert report["paper_state_modified_by_third_trade_submit_boundary"] is False
    assert report["paper_status_modified_by_third_trade_submit_boundary"] is False
    assert (data / "lsr_v2_third_trade_submit_boundary.jsonl").exists()


def test_max_orders_must_be_one(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER", max_orders=2),
    )
    assert report["decision"] == MAX_ORDER_CAP_DECISION
    assert report["third_trade_submit_ready_count"] == 0
    assert report["orders_submitted_by_third_trade_submit_boundary"] == 0


def test_preflight_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, ready=False)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"),
    )
    assert report["decision"] == PREFLIGHT_MISSING_DECISION
    assert report["submit_boundary_events"] == 0
    assert report["orders_submitted_by_third_trade_submit_boundary"] == 0


def test_invalid_payload_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, invalid=True)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"),
    )
    assert report["decision"] == PAYLOAD_INVALID_DECISION
    assert report["third_trade_submit_ready_count"] == 0
    assert report["would_submit_count"] == 0


def test_unsafe_preflight_rejected(tmp_path: Path) -> None:
    data = _seed(tmp_path, unsafe=True)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"),
    )
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert report["orders_submitted_by_third_trade_submit_boundary"] == 0
    assert any("broker_submit" in b or "would_submit" in b for b in report["blockers"])


def test_strict_cycle_scope_uses_requested_cycle(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_submit_boundary_report_from_files(
        data_dir=data,
        cycle_id="other_cycle",
        settings=_settings(submit_arm="1", submit_confirmation="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"),
    )
    assert report["cycle_id"] == "other_cycle"
    assert report["decision"] == PAYLOAD_INVALID_DECISION
    assert report["submit_boundary_events"] == 0
