from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_eligibility_gate import (
    PASS_DECISION,
    OBSERVATION_REQUIRED_DECISION,
    SECOND_TRADE_LOCKED_DECISION,
    STATE_NOT_CLEAN_DECISION,
    REJECT_DECISION,
    build_lsr_v2_second_trade_eligibility_gate_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    completed_cycles: int = 86,
    observation_pass: bool = True,
    postmortem_pass: bool = True,
    final_pass: bool = True,
    open_position: bool = False,
    status_open_positions: int = 0,
    pending_orders: int = 0,
    new_submit_cycles: list[str] | None = None,
    reentry: bool = False,
    second_trade_allowed: bool = False,
    realized_r: float = 3.8589222878,
    live_enabled: bool = False,
    observation_created_activity: bool = False,
) -> Path:
    data = tmp_path / "data"
    cycle = "pc_first"
    obs = {
        "status": "PASS" if observation_pass else "WARN",
        "decision": "LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS" if observation_pass else "KEEP_DIAGNOSTIC_LSR_V2_OBSERVATION_IN_PROGRESS",
        "cycle_id": cycle,
        "postmortem_pass": postmortem_pass,
        "closed_trade_complete": final_pass,
        "completed_observation_cycles": completed_cycles,
        "failed_observation_cycles": 0,
        "timed_out_cycles": 0,
        "new_submit_cycles": new_submit_cycles or [],
        "extra_submit_or_reentry_detected": reentry,
        "second_trade_allowed": second_trade_allowed,
        "second_trade_locked": not second_trade_allowed,
        "paper_state_consistency": not open_position,
        "paper_status_consistency": status_open_positions == 0 and pending_orders == 0 and not open_position,
        "state_open_lsr_v2_positions": 1 if open_position else 0,
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": pending_orders,
        "residual_open_position": open_position,
        "submit_execution_events_total": 1,
        "close_execution_events_total": 1,
        "realized_pnl_total": 9.6473057196,
        "realized_r": realized_r,
        "orders_submitted_by_observation": 1 if observation_created_activity else 0,
        "positions_opened_by_observation": 0,
        "positions_closed_by_observation": 0,
        "broker_submit_called_by_observation": False,
        "broker_close_called_by_observation": False,
        "paper_state_modified_by_observation": False,
        "paper_status_modified_by_observation": False,
        "live_enabled": live_enabled,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    post = {
        "status": "PASS" if postmortem_pass else "WARN",
        "decision": "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS" if postmortem_pass else "KEEP_DIAGNOSTIC_INCOMPLETE",
        "cycle_id": cycle,
        "postmortem_complete": postmortem_pass,
        "closed_trade_complete": final_pass,
        "second_trade_allowed": False,
        "state_open_lsr_v2_positions": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "realized_r": realized_r,
        "realized_pnl_total": 9.6473057196,
        "orders_submitted_by_postmortem": 0,
        "positions_opened_by_postmortem": 0,
        "positions_closed_by_postmortem": 0,
        "broker_submit_called_by_postmortem": False,
        "broker_close_called_by_postmortem": False,
        "paper_state_modified_by_postmortem": False,
        "paper_status_modified_by_postmortem": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    final = {
        "status": "PASS" if final_pass else "WARN",
        "decision": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS" if final_pass else "KEEP_DIAGNOSTIC_INCOMPLETE",
        "cycle_id": cycle,
        "closed_trade_complete": final_pass,
        "realized_r": realized_r,
        "realized_pnl_total": 9.6473057196,
        "state_open_lsr_v2_positions": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "broker_submit_called_by_final_audit": False,
        "broker_close_called_by_final_audit": False,
        "paper_state_modified_by_final_audit": False,
        "paper_status_modified_by_final_audit": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    _write_json(data / "lsr_v2_post_first_trade_observation_report.json", obs)
    _write_json(data / "lsr_v2_first_paper_trade_postmortem_report.json", post)
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", final)
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_lsr": {
                "position_id": "pos_lsr",
                "status": "OPEN" if open_position else "CLOSED",
                "open": open_position,
                "source": "lsr_v2_supervised_paper_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
            }
        }
    })
    _write_json(data / "paper_status.json", {
        "open_positions": status_open_positions,
        "pending_orders": pending_orders,
        "position_monitor": {"open_position_count": status_open_positions},
    })
    return data


def test_second_trade_eligibility_pass(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["status"] == "PASS"
    assert report["second_trade_eligible"] is True
    assert report["second_trade_execute_enabled"] is False
    assert report["orders_submitted_by_second_trade_gate"] == 0
    assert report["positions_opened_by_second_trade_gate"] == 0
    assert (data / "lsr_v2_second_trade_eligibility_gate_report.json").exists()


def test_observation_required_when_8h_not_confirmed(tmp_path: Path) -> None:
    data = _seed(tmp_path, completed_cycles=44)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == OBSERVATION_REQUIRED_DECISION
    assert "eight_hour_observation_not_confirmed" in report["blockers"]
    assert report["second_trade_eligible"] is False


def test_state_not_clean_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True, status_open_positions=1)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert "paper_state_not_clean" in report["blockers"]


def test_new_submit_or_reentry_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, new_submit_cycles=["pc_second"])
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == SECOND_TRADE_LOCKED_DECISION
    assert report["new_submit_cycles"] == ["pc_second"]
    assert report["second_trade_eligible"] is False


def test_realized_r_must_be_positive(tmp_path: Path) -> None:
    data = _seed(tmp_path, realized_r=0.0)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert "realized_r_not_positive" in report["blockers"]


def test_unsafe_flags_reject(tmp_path: Path) -> None:
    data = _seed(tmp_path, live_enabled=True)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert "unsafe_flag_detected" in report["blockers"]


def test_gate_activity_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, observation_created_activity=True)
    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert "gate_or_observation_created_activity" in report["blockers"]
