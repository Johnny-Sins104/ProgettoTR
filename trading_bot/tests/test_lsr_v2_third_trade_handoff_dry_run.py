from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_handoff_dry_run import (
    NO_CREATABLE_INTENT_DECISION,
    PAYLOAD_INVALID_DECISION,
    READY_DECISION,
    REJECT_DECISION,
    ROUTE_MISSING_DECISION,
    build_lsr_v2_third_trade_handoff_dry_run_report_from_files,
)
from trading_bot.core.lsr_v2_third_trade_route_preflight import READY_DECISION as ROUTE_READY_DECISION


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _route_report(*, ready: bool = True, unsafe: bool = False) -> dict:
    return {
        "status": "PASS" if ready else "WARN",
        "decision": ROUTE_READY_DECISION if ready else "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_OPERATOR_CONFIRMATION_MISSING",
        "cycle_id": "pc_third",
        "third_trade_eligible": True,
        "third_trade_rearm_ready": True,
        "third_trade_route_preflight_ready": ready,
        "third_trade_order_intent_ready": ready,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called_by_third_trade_route_preflight": unsafe,
        "orders_submitted_by_third_trade_route_preflight": 0,
        "positions_opened_by_third_trade_route_preflight": 0,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }


def _intent(*, creatable: bool = True, invalid: bool = False, unsafe: bool = False) -> dict:
    return {
        "event_type": "LSR_V2_THIRD_TRADE_ORDER_INTENT_PREFLIGHT",
        "cycle_id": "pc_third",
        "symbol": "BTC/USDT" if not invalid else "",
        "timeframe": "5m",
        "candidate_id": "btc_third",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "account_equity": 1000.0,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "quantity": 2.5,
        "notional": 250.0,
        "max_positions": 1,
        "would_create_order": creatable,
        "would_submit": unsafe,
        "would_submit_to_paper_broker": unsafe,
        "broker_submit_called": unsafe,
        "third_trade_submit_enabled": unsafe,
        "third_trade_execute_enabled": unsafe,
        "paper_order_submission_enabled": unsafe,
    }


def _route_event() -> dict:
    return {
        "event_type": "LSR_V2_THIRD_TRADE_ROUTE_PREFLIGHT",
        "cycle_id": "pc_third",
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "btc_third",
        "would_route": True,
        "would_submit": False,
        "broker_submit_called": False,
    }


def _seed(tmp_path: Path, *, ready: bool = True, creatable: bool = True, invalid: bool = False, unsafe: bool = False, rows: bool = True) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_third_trade_route_preflight_report.json", _route_report(ready=ready, unsafe=unsafe))
    if rows:
        _write_jsonl(data / "lsr_v2_third_trade_route_preflight.jsonl", [_route_event(), _intent(creatable=creatable, invalid=invalid, unsafe=unsafe)])
    return data


def test_route_preflight_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, ready=False)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == ROUTE_MISSING_DECISION
    assert report["handoff_dry_run_events"] == 0
    assert report["orders_submitted_by_third_trade_handoff"] == 0


def test_no_order_intent_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, rows=False)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == NO_CREATABLE_INTENT_DECISION
    assert "third_trade_order_intent_missing" in report["blockers"]


def test_no_creatable_intent_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, creatable=False)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == NO_CREATABLE_INTENT_DECISION
    assert report["creatable_order_intents"] == 0


def test_invalid_payload_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, invalid=True)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == PAYLOAD_INVALID_DECISION
    assert report["payload_valid_count"] == 0
    assert report["payload_invalid_count"] == 1


def test_handoff_dry_run_ready_builds_valid_payload_without_submit(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == READY_DECISION
    assert report["status"] == "PASS"
    assert report["payload_valid_count"] == 1
    assert report["would_create_paper_order_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_third_trade_handoff"] == 0
    assert report["positions_opened_by_third_trade_handoff"] == 0
    assert report["total_risk_amount"] == 2.5
    rows = [json.loads(line) for line in (data / "lsr_v2_third_trade_handoff_dry_run.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event_type"] == "LSR_V2_THIRD_TRADE_HANDOFF_DRY_RUN"
    assert rows[0]["payload_valid"] is True
    assert rows[0]["broker_submit_called"] is False


def test_upstream_submit_or_broker_call_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, unsafe=True)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert any("broker_submit" in blocker or "would_submit" in blocker for blocker in report["blockers"])
    assert report["orders_submitted_by_third_trade_handoff"] == 0


def test_fail_closed_disabled_rejects(tmp_path: Path) -> None:
    from trading_bot.core.lsr_v2_third_trade_handoff_dry_run import LSRV2ThirdTradeHandoffDryRunSettings
    data = _seed(tmp_path)
    settings = LSRV2ThirdTradeHandoffDryRunSettings(data_dir=str(data), fail_closed=False)
    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(data_dir=data, settings=settings)
    assert report["decision"] == REJECT_DECISION
    assert "fail_closed_disabled" in report["blockers"]
