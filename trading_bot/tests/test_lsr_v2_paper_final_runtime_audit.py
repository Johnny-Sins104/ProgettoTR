from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_final_runtime_audit import (
    OPEN_POSITION_DECISION,
    REJECT_DECISION,
    WARN_DECISION,
    build_lsr_v2_paper_final_runtime_audit_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _seed_runtime(
    tmp_path: Path,
    *,
    position_status: str = "CLOSED",
    status_open_positions: int = 0,
    extra_order: bool = False,
    live_enabled: bool = False,
) -> Path:
    data = tmp_path / "data"
    cycle = "pc_000517_99a0e0a7"
    order_id = "po_a8407626023b47cf"
    position_id = "pp_e8777c510d2f4031"
    orders = {
        order_id: {
            "order_id": order_id,
            "symbol": "BTC/USDT",
            "side": "SELL",
            "status": "FILLED",
            "filled_price": 99076.7,
            "qty": 0.008597875,
            "metadata": {
                "cycle_id": cycle,
                "execution_source": "lsr_v2_supervised_paper_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                "selected_overlay_id": "combo_loss3_dd10_side_cap",
                "live_enabled": False,
                "testnet_enabled": False,
                "exchange_broker_enabled": False,
            },
        }
    }
    if extra_order:
        orders["po_extra"] = {
            "order_id": "po_extra",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": "FILLED",
            "metadata": {"cycle_id": "pc_extra", "execution_source": "unexpected_extra_order"},
        }
    positions = {
        position_id: {
            "position_id": position_id,
            "symbol": "BTC/USDT",
            "side": "SELL",
            "status": position_status,
            "entry_price": 99076.7,
            "exit_price": 99367.46952 if position_status == "CLOSED" else None,
            "stop_loss": 99367.46952,
            "take_profit": 98495.16096,
            "qty": 0.008597875,
            "fees_paid": 2.045437796824708,
            "realized_pnl": -2.841739619569722 if position_status == "CLOSED" else 0.0,
            "close_reason": "SL" if position_status == "CLOSED" else "",
            "metadata": {
                "cycle_id": cycle,
                "source_order_id": order_id,
                "execution_source": "lsr_v2_supervised_paper_submit_execution",
                "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                "selected_overlay_id": "combo_loss3_dd10_side_cap",
                "live_enabled": False,
                "testnet_enabled": False,
                "exchange_broker_enabled": False,
            },
        }
    }
    open_count = 1 if position_status == "OPEN" else 0
    _write_json(data / "paper_state.json", {
        "balance": 1019.2088998391052,
        "equity": 1019.2088998391052,
        "realized_pnl": 19.20889983910528,
        "orders": orders,
        "positions": positions,
    })
    _write_json(data / "paper_status.json", {
        "mode": "paper",
        "market_data_mode": "replay",
        "balance": 1019.2088998391052,
        "equity": 1019.2088998391052,
        "realized_pnl": 19.20889983910528,
        "unrealized_pnl": 0.0,
        "open_positions": status_open_positions,
        "pending_orders": 0,
        "positions": [],
        "live_execution_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    lifecycle_warnings = [f"filled_order_missing_fill_event: {order_id}"]
    if position_status == "CLOSED":
        lifecycle_warnings.insert(0, f"closed_position_missing_close_event: {position_id}")
    _write_json(data / "paper_lifecycle_report.json", {
        "status": "WARN",
        "reconciliation": {
            "warnings": lifecycle_warnings,
            "errors": [],
        },
    })
    _write_json(data / "lsr_v2_supervised_paper_submit_execution_report.json", {
        "status": "PASS",
        "cycle_id": cycle,
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
        "paper_broker_adapter": "PaperBrokerAdapter",
        "live_enabled": live_enabled,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "lsr_v2_paper_status_reconciliation_report.json", {
        "status": "PASS",
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "lsr_v2_open_position_monitor_report.json", {
        "status": "PASS",
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "lsr_v2_paper_position_lifecycle_report.json", {
        "status": "PASS",
        "cycle_id": cycle,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_submit_execution.jsonl", [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": cycle,
        "submit_result": {"order_id": order_id},
        "order_submitted": True,
        "position_opened": True,
    }])
    _write_jsonl(data / "telegram_audit.jsonl", [{
        "event_type": "TELEGRAM_POSITION_CLOSE_NOTIFICATION",
        "cycle_id": "pc_000518_eb9c871a",
        "position_id": position_id,
        "status": "sent",
    }])
    _write_jsonl(data / "paper_events.jsonl", [
        {"event_type": "CYCLE_COMPLETED", "cycle_id": cycle, "open_positions": open_count},
        {"event_type": "MAX_CYCLES_REACHED", "completed_cycles": 217, "max_cycles": 217},
        {"event_type": "ENGINE_STOPPED", "lifecycle_status": "WARN"},
    ])
    return data


def test_closed_state_with_missing_tail_events_is_not_fail(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="CLOSED", status_open_positions=0)
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == WARN_DECISION
    assert report["final_state"] == "FLAT"
    assert report["recommendation"] == "proceed_to_pnl_reconciliation"
    assert report["paper_state_status_consistent"] is True
    assert report["lifecycle_warning_classification"]["true_missing_event"] == []
    assert "filled_order_missing_fill_event: po_a8407626023b47cf" in report["lifecycle_warning_classification"]["state_derived_fill_accepted"]
    assert "closed_position_missing_close_event: pp_e8777c510d2f4031" in report["lifecycle_warning_classification"]["state_derived_close_accepted"]


def test_state_status_divergence_fails(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="CLOSED", status_open_positions=1)
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == REJECT_DECISION
    assert "paper_state_status_divergence" in report["blockers"]


def test_open_position_does_not_declare_flat(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="OPEN", status_open_positions=1)
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert report["final_state"] == "OPEN_POSITION"
    assert report["decision"] == OPEN_POSITION_DECISION
    assert report["recommendation"] == "open_position_monitor_required"


def test_extra_order_is_fail(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="CLOSED", status_open_positions=0, extra_order=True)
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert "extra_order_detected" in report["blockers"]


def test_live_flag_is_fail_closed(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="CLOSED", status_open_positions=0, live_enabled=True)
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert "live_mode_enabled" in report["blockers"]


def test_final_runtime_audit_does_not_mutate_state_or_status(tmp_path: Path) -> None:
    data = _seed_runtime(tmp_path, position_status="CLOSED", status_open_positions=0)
    before_state = (data / "paper_state.json").read_text(encoding="utf-8")
    before_status = (data / "paper_status.json").read_text(encoding="utf-8")
    build_lsr_v2_paper_final_runtime_audit_report_from_files(data_dir=data)
    assert (data / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (data / "paper_status.json").read_text(encoding="utf-8") == before_status
