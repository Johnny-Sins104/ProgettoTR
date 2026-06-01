from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_two_trade_observation import (
    PASS_DECISION,
    IN_PROGRESS_DECISION,
    THIRD_SUBMIT_DECISION,
    STATE_INCONSISTENT_DECISION,
    FAILED_DECISION,
    build_lsr_v2_two_trade_observation_report_from_files,
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
    postmortem_pass: bool = True,
    open_position: bool = False,
    status_open: int = 0,
    pending_orders: int = 0,
    third_allowed: bool = False,
    third_detected: bool = False,
    submit_total: int = 2,
    close_total: int = 2,
    live: bool = False,
) -> Path:
    data = tmp_path / "data"
    report = {
        "status": "PASS" if postmortem_pass else "WARN",
        "decision": "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS" if postmortem_pass else "KEEP_DIAGNOSTIC_INCOMPLETE",
        "cycle_ids": ["pc_1", "pc_2"],
        "two_trade_postmortem_complete": postmortem_pass,
        "submit_execution_events_total": submit_total,
        "close_execution_events_total": close_total,
        "total_realized_pnl": 21.1430246906,
        "average_realized_r": 4.2286049381,
        "total_risk_amount": 5.0,
        "pnl_reconciliation_ok": True,
        "state_open_lsr_v2_positions": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "third_trade_allowed": third_allowed,
        "third_trade_locked": not third_allowed,
        "third_submit_or_reentry_detected": third_detected,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    _write_json(data / "lsr_v2_two_trade_paper_cycle_postmortem_report.json", report)
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_latest": {
                "position_id": "pos_latest",
                "cycle_id": "pc_2",
                "source": "lsr_v2_second_trade_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                "status": "OPEN" if open_position else "CLOSED",
                "open": open_position,
            }
        }
    })
    _write_json(data / "paper_status.json", {
        "open_positions": status_open,
        "pending_orders": pending_orders,
        "position_monitor": {"open_position_count": status_open},
    })
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_2"}])
    return data


def test_two_trade_observation_pass(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["third_trade_locked"] is True
    assert report["third_trade_allowed"] is False
    assert report["third_submit_or_reentry_detected"] is False
    assert report["paper_status_open_positions"] == 0
    assert report["orders_submitted_by_two_trade_observation"] == 0
    assert (data / "lsr_v2_two_trade_observation_report.json").exists()


def test_missing_postmortem_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, postmortem_pass=False)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == IN_PROGRESS_DECISION
    assert "two_trade_postmortem_not_pass" in report["blockers"]


def test_residual_open_position_blocks_as_state_inconsistent(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True, status_open=1)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == THIRD_SUBMIT_DECISION
    assert report["residual_open_position"] is True
    assert "residual_open_position" in report["blockers"]


def test_pending_orders_block_state(tmp_path: Path) -> None:
    data = _seed(tmp_path, pending_orders=1)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert "paper_status_inconsistent" in report["blockers"]


def test_third_trade_allowed_or_detected_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, third_allowed=True)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == IN_PROGRESS_DECISION
    assert "third_trade_not_locked" in report["blockers"]

    data2 = _seed(tmp_path / "x", third_detected=True)
    report2 = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data2)
    assert report2["decision"] == THIRD_SUBMIT_DECISION
    assert "third_submit_or_reentry_detected" in report2["blockers"]


def test_live_flags_fail(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)
    assert report["decision"] == FAILED_DECISION
    assert report["status"] == "FAIL"


def test_observation_cycle_counts_are_reported(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_two_trade_observation_report_from_files(
        data_dir=data,
        completed_observation_cycles=3,
        failed_observation_cycles=0,
        timed_out_cycles=0,
        cycle_results=[{"cycle_index": 1, "returncode": 0}],
    )
    assert report["decision"] == PASS_DECISION
    assert report["completed_observation_cycles"] == 3
    assert report["cycle_results"][0]["cycle_index"] == 1
