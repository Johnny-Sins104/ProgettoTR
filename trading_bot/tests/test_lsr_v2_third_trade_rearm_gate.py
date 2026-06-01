from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_rearm_gate import (
    CONFIRMATION_MISSING_DECISION,
    ELIGIBILITY_MISSING_DECISION,
    MAX_ORDER_CAP_DECISION,
    NOT_ENABLED_DECISION,
    PASS_DECISION,
    REQUIRED_REARM_CONFIRMATION,
    STATE_NOT_CLEAN_DECISION,
    LSRV2ThirdTradeRearmSettings,
    build_lsr_v2_third_trade_rearm_gate_report_from_files,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _base_data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    _write(data / "paper_state.json", {"orders": {}, "positions": {}, "balance": 1021.1430246906})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})
    (data / "paper_events.jsonl").write_text(
        json.dumps({"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_000500_third_wait"}) + "\n",
        encoding="utf-8",
    )
    _write(data / "lsr_v2_third_trade_eligibility_gate_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_PAPER_TRADE_ELIGIBILITY_PASS",
        "third_trade_eligible": True,
        "third_trade_gate_ready": True,
        "third_trade_locked": True,
        "third_trade_allowed": False,
        "third_submit_or_reentry_detected": False,
        "four_hour_observation_pass": True,
        "eight_hour_observation_pass": True,
        "completed_observation_cycles": 85,
        "failed_observation_cycles": 0,
        "timed_out_cycles": 0,
        "telegram_position_monitor_ready": True,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "residual_open_position": False,
        "total_realized_pnl": 21.1430246906,
        "average_realized_r": 4.2286049381,
        "total_risk_amount": 5.0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    })
    return data


def test_rearm_not_enabled_is_warn_and_non_mutating(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == NOT_ENABLED_DECISION
    assert report["third_trade_rearm_ready"] is False
    assert report["orders_submitted_by_third_trade_rearm_gate"] == 0
    assert report["positions_opened_by_third_trade_rearm_gate"] == 0
    assert report["paper_order_submission_enabled"] is False


def test_rearm_confirmation_missing_is_warn(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    settings = LSRV2ThirdTradeRearmSettings(data_dir=str(data), rearm_enable="1", rearm_confirmation="wrong")
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["third_trade_rearm_enabled"] is True
    assert report["third_trade_rearm_confirmation_ok"] is False
    assert report["third_trade_execute_enabled"] is False


def test_rearm_ready_with_operator_confirmation(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    settings = LSRV2ThirdTradeRearmSettings(
        data_dir=str(data),
        rearm_enable="1",
        rearm_confirmation=REQUIRED_REARM_CONFIRMATION,
        max_orders=1,
    )
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["third_trade_rearm_ready"] is True
    assert report["candidate_wait_gate_ready"] is True
    assert report["third_trade_allowed"] is False
    assert report["third_trade_submit_enabled"] is False
    assert report["third_trade_execute_enabled"] is False
    assert report["orders_submitted_by_third_trade_rearm_gate"] == 0
    assert report["positions_opened_by_third_trade_rearm_gate"] == 0


def test_missing_eligibility_blocks_rearm(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})
    settings = LSRV2ThirdTradeRearmSettings(data_dir=str(data), rearm_enable="1", rearm_confirmation=REQUIRED_REARM_CONFIRMATION)
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert report["decision"] == ELIGIBILITY_MISSING_DECISION
    assert "third_trade_eligibility_not_pass" in report["blockers"]
    assert report["third_trade_rearm_ready"] is False


def test_open_position_blocks_rearm(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    _write(data / "paper_state.json", {
        "orders": {},
        "positions": {
            "p1": {
                "symbol": "BTC/USDT",
                "status": "OPEN",
                "open": True,
                "metadata": {"paper_order_source": "lsr_v2_third_trade_submit_execution"},
            }
        },
    })
    _write(data / "paper_status.json", {"open_positions": 1, "pending_orders": 0})
    settings = LSRV2ThirdTradeRearmSettings(data_dir=str(data), rearm_enable="1", rearm_confirmation=REQUIRED_REARM_CONFIRMATION)
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert report["residual_open_position"] is True
    assert report["third_trade_rearm_ready"] is False


def test_max_orders_must_remain_one(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    settings = LSRV2ThirdTradeRearmSettings(
        data_dir=str(data),
        rearm_enable="1",
        rearm_confirmation=REQUIRED_REARM_CONFIRMATION,
        max_orders=2,
    )
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert report["decision"] == MAX_ORDER_CAP_DECISION
    assert "max_orders_must_equal_1" in report["blockers"]
    assert report["third_trade_rearm_ready"] is False


def test_writes_report_and_jsonl(tmp_path: Path) -> None:
    data = _base_data(tmp_path)
    settings = LSRV2ThirdTradeRearmSettings(data_dir=str(data), rearm_enable="1", rearm_confirmation=REQUIRED_REARM_CONFIRMATION)
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(data_dir=data, settings=settings)
    assert (data / "lsr_v2_third_trade_rearm_gate_report.json").exists()
    assert (data / "lsr_v2_third_trade_rearm_gate.jsonl").exists()
    assert json.loads((data / "lsr_v2_third_trade_rearm_gate_report.json").read_text())["decision"] == report["decision"]
