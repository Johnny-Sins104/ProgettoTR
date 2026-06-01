from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_two_trade_paper_cycle_postmortem import (
    PASS_DECISION,
    THIRD_SUBMIT_DECISION,
    RESIDUAL_POSITION_DECISION,
    PNL_RECONCILIATION_DECISION,
    FAILED_DECISION,
    build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed(tmp_path: Path, *, open_position: bool = False, second_pnl: float = 11.495718971, submit_total_override: int | None = None, live: bool = False) -> Path:
    data = tmp_path / "data"
    first = {
        "status": "PASS",
        "decision": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": "pc_first",
        "submit_execution_events": 1,
        "close_execution_events": 1,
        "realized_pnl_total": 9.6473057196,
        "realized_r": 3.8589222878,
        "total_risk_amount": 2.5,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "live_enabled": False,
    }
    first_pm = {
        "status": "PASS",
        "decision": "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS",
        "cycle_id": "pc_first",
        "postmortem_complete": True,
        "extra_submit_or_reentry_detected": False,
        "realized_pnl_total": 9.6473057196,
        "realized_r": 3.8589222878,
    }
    second = {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": "pc_second",
        "second_closed_trade_complete": True,
        "submit_execution_events": 1 if submit_total_override is None else submit_total_override - 1,
        "close_execution_events": 1,
        "realized_pnl_total": second_pnl,
        "realized_r": round(second_pnl / 2.5, 10) if second_pnl else 0.0,
        "total_risk_amount": 2.5,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "third_submit_or_reentry_detected": False,
        "live_enabled": live,
    }
    obs = {
        "status": "PASS",
        "decision": "LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS",
        "completed_observation_cycles": 86,
        "extra_submit_or_reentry_detected": False,
    }
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", first)
    _write_json(data / "lsr_v2_first_paper_trade_postmortem_report.json", first_pm)
    _write_json(data / "lsr_v2_second_closed_trade_final_audit_report.json", second)
    _write_json(data / "lsr_v2_post_first_trade_observation_report.json", obs)
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_first": {"source": "lsr_v2_supervised_paper_submit_execution", "cycle_id": "pc_first", "status": "CLOSED", "open": False},
            "pos_second": {"source": "lsr_v2_second_trade_submit_execution", "cycle_id": "pc_second", "status": "OPEN" if open_position else "CLOSED", "open": open_position, "trade_sequence": "SECOND"},
        }
    })
    _write_json(data / "paper_status.json", {"open_positions": 1 if open_position else 0, "pending_orders": 0})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_second"}])
    return data


def test_two_trade_postmortem_passes(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["two_trade_postmortem_complete"] is True
    assert report["submit_execution_events_total"] == 2
    assert report["close_execution_events_total"] == 2
    assert report["total_realized_pnl"] == round(9.6473057196 + 11.495718971, 10)
    assert report["total_realized_r"] == round((9.6473057196 + 11.495718971) / 5.0, 10)
    assert report["third_trade_allowed"] is False
    assert report["next_step_observation_required"] is True
    assert report["orders_submitted_by_two_trade_postmortem"] == 0
    assert report["paper_state_modified_by_two_trade_postmortem"] is False


def test_passes_when_paper_state_keeps_only_latest_closed_position(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    _write_json(data / "paper_state.json", {
        "positions": {
            "pos_second": {
                "source": "lsr_v2_second_trade_submit_execution",
                "cycle_id": "pc_second",
                "status": "CLOSED",
                "open": False,
                "trade_sequence": "SECOND",
            }
        }
    })
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["paper_state_consistency"] is True
    assert report["state_closed_lsr_v2_positions"] == 1
    assert report["paper_state_closed_history_complete"] is False
    assert report["two_trade_postmortem_complete"] is True


def test_residual_open_position_warns(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["decision"] in {THIRD_SUBMIT_DECISION, RESIDUAL_POSITION_DECISION}
    assert report["residual_open_position"] is True


def test_third_submit_detected(tmp_path: Path) -> None:
    data = _seed(tmp_path, submit_total_override=3)
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == THIRD_SUBMIT_DECISION
    assert report["third_submit_or_reentry_detected"] is True


def test_zero_second_pnl_warns(tmp_path: Path) -> None:
    data = _seed(tmp_path, second_pnl=0.0)
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == PNL_RECONCILIATION_DECISION
    assert report["pnl_reconciliation_ok"] is False


def test_missing_first_postmortem_warns_incomplete(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    (data / "lsr_v2_first_paper_trade_postmortem_report.json").write_text("{}\n", encoding="utf-8")
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert "first_trade_postmortem_not_pass" in report["blockers"]


def test_live_flag_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
