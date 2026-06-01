from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_post_first_trade_observation import (
    PASS_DECISION,
    IN_PROGRESS_DECISION,
    REENTRY_DETECTED_DECISION,
    NEW_SUBMIT_DETECTED_DECISION,
    STATE_INCONSISTENT_DECISION,
    REJECT_DECISION,
    build_lsr_v2_post_first_trade_observation_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    open_position: bool = False,
    postmortem_pass: bool = True,
    second_trade_allowed: bool = False,
    extra_submit_cycle: bool = False,
    status_open_positions: int = 0,
    live_flag: bool = False,
) -> Path:
    data = tmp_path / "data"
    cycle = "pc_closed"
    postmortem = {
        "status": "PASS" if postmortem_pass else "WARN",
        "decision": "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS" if postmortem_pass else "KEEP_DIAGNOSTIC_INCOMPLETE",
        "cycle_id": cycle,
        "postmortem_complete": postmortem_pass,
        "closed_trade_complete": postmortem_pass,
        "next_step_observation_required": True,
        "second_trade_allowed": second_trade_allowed,
        "submit_execution_events": 1,
        "close_execution_events": 1,
        "state_open_lsr_v2_positions": 1 if open_position else 0,
        "state_closed_lsr_v2_positions": 1,
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": 0,
        "residual_open_position": open_position,
        "extra_submit_or_reentry_detected": False,
        "realized_pnl_total": 9.6473057196,
        "realized_r": 3.8589222878,
        "live_enabled": live_flag,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    _write_json(data / "lsr_v2_first_paper_trade_postmortem_report.json", postmortem)
    _write_jsonl(data / "lsr_v2_first_paper_trade_postmortem.jsonl", [{"event_type": "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM", **postmortem}])
    final = {
        "status": "PASS",
        "decision": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": cycle,
        "closed_trade_complete": True,
        "realized_pnl_total": 9.6473057196,
        "realized_r": 3.8589222878,
        "total_risk_amount": 2.5,
        "state_open_lsr_v2_positions": 0,
        "state_closed_lsr_v2_positions": 1,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", final)
    submit_rows = [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": cycle,
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
    }]
    if extra_submit_cycle:
        submit_rows.append({
            "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
            "cycle_id": "pc_second",
            "orders_submitted_by_lsr_v2_execution": 1,
            "positions_opened_by_lsr_v2_execution": 1,
            "broker_submit_called": True,
        })
    _write_jsonl(data / "lsr_v2_supervised_paper_submit_execution.jsonl", submit_rows)
    _write_json(data / "lsr_v2_supervised_paper_submit_execution_report.json", {
        "cycle_id": cycle,
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_close_execution.jsonl", [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION",
        "cycle_id": cycle,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "broker_close_called": True,
    }])
    _write_json(data / "lsr_v2_supervised_paper_close_execution_report.json", {
        "cycle_id": cycle,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "broker_close_called": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_1": {
                "position_id": "pos_1",
                "cycle_id": cycle,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": "OPEN" if open_position else "CLOSED",
                "open": open_position,
                "source": "lsr_v2_supervised_paper_submit_execution",
            }
        }
    })
    _write_json(data / "paper_status.json", {
        "open_positions": status_open_positions,
        "pending_orders": 0,
        "position_monitor": {"open_position_count": status_open_positions},
    })
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": cycle}])
    return data


def test_observation_pass(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["second_trade_allowed"] is False
    assert report["second_trade_locked"] is True
    assert report["extra_submit_or_reentry_detected"] is False
    assert report["state_open_lsr_v2_positions"] == 0
    assert report["paper_status_open_positions"] == 0
    assert report["orders_submitted_by_observation"] == 0
    assert (data / "lsr_v2_post_first_trade_observation_report.json").exists()


def test_missing_or_incomplete_postmortem_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, postmortem_pass=False)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == IN_PROGRESS_DECISION
    assert "postmortem_not_pass" in report["blockers"]


def test_residual_position_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True, status_open_positions=1)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == REENTRY_DETECTED_DECISION
    assert report["residual_open_position"] is True


def test_extra_submit_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, extra_submit_cycle=True)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == NEW_SUBMIT_DETECTED_DECISION
    assert report["new_submit_cycles"] == ["pc_second"]


def test_state_inconsistency_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, status_open_positions=1)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert "paper_state_status_inconsistent" in report["blockers"]


def test_live_flag_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, live_flag=True)
    report = build_lsr_v2_post_first_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"
    assert "unsafe_flag_detected" in report["blockers"]
