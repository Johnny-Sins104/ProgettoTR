from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_rearm_gate import (
    CANDIDATE_WAIT_DECISION,
    CONFIRMATION_MISSING_DECISION,
    NOT_ENABLED_DECISION,
    PASS_DECISION,
    STATE_NOT_CLEAN_DECISION,
    REJECT_DECISION,
    LSRV2SecondTradeRearmSettings,
    build_lsr_v2_second_trade_rearm_gate_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _eligibility(cycle_id: str = "pc_second") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS",
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_locked": True,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "observation_pass": True,
        "four_hour_observation_pass": True,
        "eight_hour_observation_pass": True,
        "completed_observation_cycles": 86,
        "failed_observation_cycles": 0,
        "timed_out_cycles": 0,
        "new_submit_cycles": [],
        "extra_submit_or_reentry_detected": False,
        "paper_state_consistency": True,
        "paper_status_consistency": True,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
        "realized_pnl_total": 9.6473057196,
        "realized_r": 3.8589222878,
        "broker_submit_called_by_second_trade_gate": False,
        "orders_submitted_by_second_trade_gate": 0,
        "positions_opened_by_second_trade_gate": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }


def _seed(tmp_path: Path, *, clean: bool = True, live: bool = False) -> Path:
    data = tmp_path / "data"
    elig = _eligibility()
    if live:
        elig["live_enabled"] = True
    _write_json(data / "lsr_v2_second_trade_eligibility_gate_report.json", elig)
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
    _write_json(data / "paper_status.json", {
        "open_positions": 0 if clean else 1,
        "pending_orders": 0,
        "position_monitor": {"open_position_count": 0 if clean else 1},
    })
    return data


def _candidate(cycle_id: str = "pc_second") -> dict:
    return {
        "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "btc_second",
        "candidate_ready": True,
        "would_submit": False,
        "broker_submit_called": False,
    }


def _bridge(cycle_id: str = "pc_second", *, would_route: bool = True) -> dict:
    return {
        "event_type": "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "btc_second",
        "candidate_ready": True,
        "would_route": would_route,
        "would_submit": False,
        "broker_submit_called": False,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
    }


def _settings(*, enable: bool, confirmation: bool = True, max_orders: int = 1) -> LSRV2SecondTradeRearmSettings:
    return LSRV2SecondTradeRearmSettings(
        rearm_enable="1" if enable else "",
        rearm_confirmation="I_UNDERSTAND_SECOND_PAPER_TRADE_DIAGNOSTIC_ONLY" if confirmation else "WRONG",
        max_orders=max_orders,
    )


def test_not_enabled_blocks_but_keeps_fail_closed(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=False))
    assert report["decision"] == NOT_ENABLED_DECISION
    assert report["status"] == "WARN"
    assert report["second_trade_eligible"] is True
    assert report["second_trade_execute_enabled"] is False
    assert report["orders_submitted_by_second_trade_rearm_gate"] == 0
    assert report["positions_opened_by_second_trade_rearm_gate"] == 0


def test_confirmation_missing_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True, confirmation=False))
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["candidate_wait_gate_ready"] is False


def test_rearm_waits_for_candidate_when_no_runtime_candidate(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    _append_jsonl(data / "paper_events.jsonl", {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_second"})
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == CANDIDATE_WAIT_DECISION
    assert report["status"] == "PASS"
    assert report["candidate_wait_gate_ready"] is True
    assert report["second_trade_rearm_ready"] is False
    assert report["runtime_candidate_ready_events"] == 0
    assert (data / "lsr_v2_second_trade_rearm_gate_report.json").exists()


def test_rearm_ready_when_current_cycle_candidate_or_route_visible(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    events = data / "paper_events.jsonl"
    _append_jsonl(events, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_old"})
    _append_jsonl(events, _candidate("pc_old"))
    _append_jsonl(events, _bridge("pc_old"))
    _append_jsonl(events, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_second"})
    _append_jsonl(events, _candidate("pc_second"))
    _append_jsonl(events, _bridge("pc_second"))
    _append_jsonl(events, {"event_type": "LSR_V2_PAPER_ORDER_INTENT_AUDIT", "cycle_id": "pc_second", "symbol": "BTC/USDT", "candidate_id": "btc_second", "would_submit": False})

    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == PASS_DECISION
    assert report["status"] == "PASS"
    assert report["cycle_id"] == "pc_second"
    assert report["runtime_candidate_events"] == 1
    assert report["runtime_candidate_ready_events"] == 1
    assert report["runtime_bridge_events"] == 1
    assert report["runtime_would_route_count"] == 1
    assert report["order_intent_events"] == 1
    assert report["historical_lsr_v2_events"] == 2
    assert report["would_submit_count"] == 0
    assert report["second_trade_execute_enabled"] is False


def test_state_not_clean_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, clean=False)
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert "paper_state_not_clean" in report["blockers"]
    assert report["state_open_lsr_v2_positions"] == 1


def test_unsafe_flag_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True))
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert "unsafe_flag_detected" in report["blockers"]


def test_max_orders_must_remain_one(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=data, settings=_settings(enable=True, max_orders=2))
    assert report["decision"] == REJECT_DECISION
    assert "max_orders_must_equal_1" in report["blockers"]
