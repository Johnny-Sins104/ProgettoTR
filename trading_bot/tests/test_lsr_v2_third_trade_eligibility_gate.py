from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_eligibility_gate import (
    PASS_DECISION,
    OBSERVATION_INSUFFICIENT_DECISION,
    STATE_NOT_CLEAN_DECISION_CANONICAL,
    POSTMORTEM_MISSING_DECISION,
    TELEGRAM_NOT_READY_DECISION,
    THIRD_TRADE_NOT_LOCKED_DECISION,
    REENTRY_DETECTED_DECISION,
    FAILED_DECISION,
    build_lsr_v2_third_trade_eligibility_gate_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    postmortem_pass: bool = True,
    observation_pass: bool = True,
    completed_cycles: int = 85,
    failed_cycles: int = 0,
    timed_out_cycles: int = 0,
    third_locked: bool = True,
    third_allowed: bool = False,
    third_detected: bool = False,
    open_position: bool = False,
    pending_orders: int = 0,
    telegram_monitor: bool = True,
    live: bool = False,
) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_two_trade_paper_cycle_postmortem_report.json", {
        "status": "PASS" if postmortem_pass else "WARN",
        "decision": "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS" if postmortem_pass else "KEEP_DIAGNOSTIC_INCOMPLETE",
        "cycle_ids": ["pc_1", "pc_2"],
        "two_trade_postmortem_complete": postmortem_pass,
        "submit_execution_events_total": 2,
        "close_execution_events_total": 2,
        "total_realized_pnl": 21.1430246906,
        "average_realized_r": 4.2286049381,
        "total_risk_amount": 5.0,
        "pnl_reconciliation_ok": True,
        "third_trade_allowed": third_allowed,
        "third_trade_locked": third_locked,
        "third_submit_or_reentry_detected": third_detected,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    })
    _write_json(data / "lsr_v2_two_trade_observation_report.json", {
        "status": "PASS" if observation_pass else "WARN",
        "decision": "LSR_V2_TWO_TRADE_OBSERVATION_PASS" if observation_pass else "KEEP_DIAGNOSTIC_IN_PROGRESS",
        "completed_observation_cycles": completed_cycles,
        "failed_observation_cycles": failed_cycles,
        "timed_out_cycles": timed_out_cycles,
        "cycle_ids": ["pc_1", "pc_2"],
        "submit_execution_events_total": 2,
        "close_execution_events_total": 2,
        "total_realized_pnl": 21.1430246906,
        "average_realized_r": 4.2286049381,
        "total_risk_amount": 5.0,
        "pnl_reconciliation_ok": True,
        "third_trade_allowed": third_allowed,
        "third_trade_locked": third_locked,
        "third_submit_or_reentry_detected": third_detected,
        "paper_status_open_positions": 1 if open_position else 0,
        "paper_status_pending_orders": pending_orders,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    })
    if telegram_monitor:
        _write_json(data / "lsr_v2_telegram_position_monitor_bridge_report.json", {
            "status": "PASS",
            "decision": "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_NO_OPEN_POSITION",
            "stale_guard": {"guard_enabled": True},
            "open_position_candidate_count": 0,
        })
    _write_json(data / "lsr_v2_telegram_notification_bridge_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_READY_DRY_RUN",
    })
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_latest": {
                "position_id": "pos_latest",
                "source": "lsr_v2_second_trade_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                "status": "OPEN" if open_position else "CLOSED",
                "open": open_position,
            }
        },
        "orders": {},
    })
    _write_json(data / "paper_status.json", {
        "open_positions": 1 if open_position else 0,
        "pending_orders": pending_orders,
        "live_enabled": live,
    })
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_2"}])
    return data


def test_third_trade_eligibility_pass(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["third_trade_eligible"] is True
    assert report["four_hour_observation_pass"] is True
    assert report["eight_hour_observation_pass"] is True
    assert report["third_trade_submit_enabled"] is False
    assert report["orders_submitted_by_third_trade_gate"] == 0
    assert (data / "lsr_v2_third_trade_eligibility_gate_report.json").exists()


def test_observation_under_8h_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, completed_cycles=43)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == OBSERVATION_INSUFFICIENT_DECISION
    assert report["four_hour_observation_pass"] is True
    assert report["eight_hour_observation_pass"] is False
    assert "eight_hour_observation_not_pass" in report["blockers"]


def test_state_not_clean_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == STATE_NOT_CLEAN_DECISION_CANONICAL
    assert report["residual_open_position"] is True
    assert "residual_open_position" in report["blockers"]


def test_pending_orders_block(tmp_path: Path) -> None:
    data = _seed(tmp_path, pending_orders=1)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == STATE_NOT_CLEAN_DECISION_CANONICAL
    assert report["pending_order_detected"] is True


def test_missing_postmortem_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, postmortem_pass=False)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == POSTMORTEM_MISSING_DECISION
    assert "two_trade_postmortem_not_pass" in report["blockers"]


def test_telegram_monitor_not_ready_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, telegram_monitor=False)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == TELEGRAM_NOT_READY_DECISION
    assert "telegram_position_monitor_not_ready" in report["blockers"]


def test_third_not_locked_and_reentry_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, third_locked=False, third_allowed=True)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == THIRD_TRADE_NOT_LOCKED_DECISION
    assert "third_trade_not_locked" in report["blockers"]

    data2 = _seed(tmp_path / "detected", third_detected=True)
    report2 = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data2)
    assert report2["decision"] == REENTRY_DETECTED_DECISION
    assert "third_submit_or_reentry_detected" in report2["blockers"]


def test_live_flag_fails(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == FAILED_DECISION
    assert report["status"] == "FAIL"
    assert "live_enabled" in report["blockers"]
