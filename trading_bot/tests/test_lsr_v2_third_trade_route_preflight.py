from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_route_preflight import (
    CANDIDATE_MISSING_DECISION,
    OPERATOR_CONFIRMATION_MISSING_DECISION,
    READY_DECISION,
    REARM_MISSING_DECISION,
    STATE_NOT_CLEAN_DECISION,
    REJECT_DECISION,
    LSRV2ThirdTradeRoutePreflightSettings,
    build_lsr_v2_third_trade_route_preflight_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _eligibility(cycle_id: str = "pc_third") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_PAPER_TRADE_ELIGIBILITY_PASS",
        "cycle_id": cycle_id,
        "third_trade_eligible": True,
        "observation_pass": True,
        "four_hour_observation_pass": True,
        "eight_hour_observation_pass": True,
        "paper_state_consistency": True,
        "paper_status_consistency": True,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
        "extra_submit_or_reentry_detected": False,
        "realized_r": 3.85,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "orders_submitted_by_third_trade_gate": 0,
        "positions_opened_by_third_trade_gate": 0,
    }


def _rearm(cycle_id: str = "pc_third", *, ready: bool = True, live: bool = False) -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_TRADE_REARM_READY_DIAGNOSTIC" if ready else "LSR_V2_THIRD_TRADE_CANDIDATE_WAIT_GATE_READY",
        "cycle_id": cycle_id,
        "third_trade_eligible": True,
        "candidate_wait_gate_ready": True,
        "third_trade_rearm_ready": ready,
        "third_trade_rearm_enabled": True,
        "third_trade_rearm_confirmation_ok": True,
        "third_trade_execute_enabled": False,
        "third_trade_submit_enabled": False,
        "runtime_candidate_ready_events": 1 if ready else 0,
        "runtime_bridge_events": 4,
        "runtime_would_route_count": 0,
        "orders_submitted_by_third_trade_rearm_gate": 0,
        "positions_opened_by_third_trade_rearm_gate": 0,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }


def _candidate(cycle_id: str = "pc_third") -> dict:
    return {
        "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "btc_third",
        "candidate_ready": True,
        "retest_ready": True,
        "side": "BUY",
        "levels": {"entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0},
        "would_submit": False,
        "broker_submit_called": False,
    }


def _bridge(cycle_id: str = "pc_third", *, would_route: bool = False) -> dict:
    return {
        "event_type": "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "btc_third",
        "runtime_cycle_scoped": True,
        "candidate_ready": True,
        "would_route": would_route,
        "would_submit": False,
        "broker_submit_called": False,
    }


def _seed(tmp_path: Path, *, clean: bool = True, rearm_ready: bool = True, live: bool = False, candidate: bool = True) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_third_trade_eligibility_gate_report.json", _eligibility())
    _write_json(data / "lsr_v2_third_trade_rearm_gate_report.json", _rearm(ready=rearm_ready, live=live))
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_1": {
                "position_id": "pos_1",
                "status": "CLOSED" if clean else "OPEN",
                "open": not clean,
                "source": "lsr_v2_supervised_paper_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
            }
        }
    })
    _write_json(data / "paper_status.json", {"open_positions": 0 if clean else 1, "pending_orders": 0})
    events = data / "paper_events.jsonl"
    _append_jsonl(events, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_old"})
    _append_jsonl(events, _candidate("pc_old"))
    _append_jsonl(events, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_third"})
    if candidate:
        _append_jsonl(events, _candidate("pc_third"))
    _append_jsonl(events, _bridge("pc_third", would_route=False))
    return data


def _settings(*, enable: bool, confirmation: bool = True, max_orders: int = 1) -> LSRV2ThirdTradeRoutePreflightSettings:
    return LSRV2ThirdTradeRoutePreflightSettings(
        route_enable="1" if enable else "",
        route_confirmation="I_UNDERSTAND_THIRD_PAPER_TRADE_ROUTE_ONLY" if confirmation else "WRONG",
        max_orders=max_orders,
    )


def test_route_confirmation_required_even_with_candidate(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=False))
    assert report["decision"] == OPERATOR_CONFIRMATION_MISSING_DECISION
    assert report["third_trade_route_preflight_ready"] is False
    assert report["orders_submitted_by_third_trade_route_preflight"] == 0
    assert report["positions_opened_by_third_trade_route_preflight"] == 0


def test_confirmation_wrong_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True, confirmation=False))
    assert report["decision"] == OPERATOR_CONFIRMATION_MISSING_DECISION
    assert report["third_trade_route_confirmation_ok"] is False


def test_rearm_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, rearm_ready=False)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == REARM_MISSING_DECISION
    assert "third_trade_rearm_not_ready" in report["blockers"]


def test_candidate_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, candidate=False)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == CANDIDATE_MISSING_DECISION
    assert "third_trade_candidate_missing" in report["blockers"]


def test_state_not_clean_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, clean=False)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert "paper_state_not_clean" in report["blockers"]
    assert report["state_open_lsr_v2_positions"] == 1


def test_route_preflight_pass_builds_third_trade_order_intent(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == READY_DECISION
    assert report["status"] == "PASS"
    assert report["third_trade_would_route_count"] == 1
    assert report["third_trade_order_intent_events"] == 1
    assert report["would_create_order_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["third_trade_execute_enabled"] is False
    assert report["third_trade_submit_enabled"] is False
    assert report["paper_order_submission_enabled"] is False
    assert report["total_risk_amount"] == 2.5
    assert (data / "lsr_v2_third_trade_route_preflight_report.json").exists()
    rows = [json.loads(line) for line in (data / "lsr_v2_third_trade_route_preflight.jsonl").read_text().splitlines()]
    assert [r["event_type"] for r in rows] == ["LSR_V2_THIRD_TRADE_ROUTE_PREFLIGHT", "LSR_V2_THIRD_TRADE_ORDER_INTENT_PREFLIGHT"]


def test_unsafe_or_max_orders_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == REJECT_DECISION
    assert "unsafe_upstream_flag_detected" in report["blockers"]
    data2 = _seed(tmp_path / "two")
    report2 = build_lsr_v2_third_trade_route_preflight_report_from_files(data_dir=data2, settings=_settings(enable=True, max_orders=2))
    assert report2["decision"] == REJECT_DECISION
    assert "max_orders_must_equal_1" in report2["blockers"]
