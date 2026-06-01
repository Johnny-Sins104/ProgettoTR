from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_bounded_multi_order_session import (
    ARM_ENV,
    CONFIRMATION_ENV,
    CONFIRMATION_PHRASE,
    BLOCKED_DECISION,
    OPERATOR_REQUIRED_DECISION,
    READY_DECISION,
    REJECT_DECISION,
    build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files,
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
    orders: int = 1,
    open_positions: int = 0,
    pending_orders: int = 0,
    duplicate_cycle: bool = False,
    pnl_status: str = "WARN",
    live_enabled: bool = False,
    kill_switch: bool = False,
    candidate_cycle: str = "pc_000734_10ee70d8",
) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_paper_final_runtime_audit_report.json", {
        "status": "WARN",
        "decision": "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_WARN_NON_BLOCKING",
        "final_state": "FLAT" if open_positions == 0 else "OPEN_POSITION",
        "paper_state_status_consistent": pending_orders == 0,
        "lifecycle_warning_classification": {"true_missing_event": []},
    })
    _write_json(data / "lsr_v2_paper_realized_pnl_reconciliation_report.json", {
        "status": pnl_status,
        "reconciliation_status": pnl_status,
        "decision": "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_WARN_NON_BLOCKING" if pnl_status != "FAIL" else "REJECT_LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_FAILED",
    })
    _write_json(data / "lsr_v2_second_paper_order_gate_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_PAPER_ORDER_GATE_READY_DEFAULT_OFF",
        "second_order_gate_ready": True,
        "live_enabled": live_enabled,
    })
    order_rows = {}
    for idx in range(orders):
        cycle = candidate_cycle if duplicate_cycle and idx == orders - 1 else f"pc_{517 + idx:06d}_first"
        order_rows[f"po_{idx}"] = {
            "order_id": f"po_{idx}",
            "status": "PENDING" if idx < pending_orders else "FILLED",
            "metadata": {"cycle_id": cycle, "execution_source": "lsr_v2_supervised_paper_submit_execution"},
        }
    position_rows = {}
    for idx in range(max(1, open_positions)):
        position_rows[f"pp_{idx}"] = {
            "position_id": f"pp_{idx}",
            "status": "OPEN" if idx < open_positions else "CLOSED",
            "open": idx < open_positions,
            "metadata": {"cycle_id": "pc_000517_first", "execution_source": "lsr_v2_supervised_paper_submit_execution"},
        }
    _write_json(data / "paper_state.json", {
        "kill_switch": kill_switch,
        "orders": order_rows,
        "positions": position_rows,
    })
    _write_json(data / "paper_status.json", {
        "kill_switch": kill_switch,
        "open_positions": open_positions,
        "pending_orders": pending_orders,
        "live_enabled": live_enabled,
    })
    _write_jsonl(data / "paper_events.jsonl", [
        {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_000733_prev"},
        {
            "event_type": "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT",
            "cycle_id": candidate_cycle,
            "candidate_ready": True,
            "would_route": True,
            "candidate_id": "candidate_multi",
            "symbol": "BTC/USDT",
            "side": "SELL",
            "entry_price": 99076.7,
            "stop_loss": 99367.46952,
            "take_profit": 98495.16096,
        },
    ])
    return data


def _arm(monkeypatch) -> None:
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)


def test_first_order_session_allowed_when_all_gates_satisfied(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, orders=0)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == READY_DECISION
    assert report["multi_order_session_ready"] is True
    assert report["session_orders"] == 0


def test_second_order_blocked_while_open_when_flat_required(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, orders=1, open_positions=1)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == BLOCKED_DECISION
    assert "require_flat_before_next_blocked" in report["blockers"]


def test_second_order_allowed_after_flat_reconciliation_and_cooldown(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, orders=1, open_positions=0, candidate_cycle="pc_000734_next")
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == READY_DECISION
    assert report["session_orders"] == 1
    assert report["cooldown_satisfied"] is True


def test_third_order_blocked_by_max_orders(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, orders=2)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == BLOCKED_DECISION
    assert "max_orders_per_session_reached" in report["blockers"]


def test_duplicate_cycle_id_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, orders=1, duplicate_cycle=True)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == BLOCKED_DECISION
    assert "duplicate_cycle_id" in report["blockers"]


def test_state_status_divergence_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, pending_orders=1)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == BLOCKED_DECISION
    assert "paper_state_status_divergence" in report["blockers"]


def test_pnl_unreconciled_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, pnl_status="FAIL")
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == BLOCKED_DECISION
    assert "pnl_unreconciled_or_fail" in report["blockers"]


def test_live_flag_rejects(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, live_enabled=True)
    _arm(monkeypatch)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == REJECT_DECISION
    assert report["status"] == "FAIL"


def test_operator_env_absent_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.delenv(ARM_ENV, raising=False)
    monkeypatch.delenv(CONFIRMATION_ENV, raising=False)
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["decision"] == OPERATOR_REQUIRED_DECISION
    assert "operator_confirmation_missing" in report["blockers"]


def test_readiness_never_calls_broker_or_mutates_state(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    _arm(monkeypatch)
    before_state = (data / "paper_state.json").read_text(encoding="utf-8")
    before_status = (data / "paper_status.json").read_text(encoding="utf-8")
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(data_dir=data)
    assert report["read_only_safety"]["broker_submit_called_by_readiness"] is False
    assert report["read_only_safety"]["orders_submitted_by_readiness"] == 0
    assert (data / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (data / "paper_status.json").read_text(encoding="utf-8") == before_status
