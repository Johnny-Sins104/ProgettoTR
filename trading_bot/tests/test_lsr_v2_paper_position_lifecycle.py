from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_paper_position_lifecycle import (  # type: ignore
    EVENT_TYPE,
    EXECUTION_EVENT_TYPE,
    READY_DECISION,
    POSITION_NOT_FOUND_DECISION,
    STATE_INCONSISTENT_DECISION,
    REJECT_DECISION,
    build_lsr_v2_paper_position_lifecycle_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _execution_row(cycle_id: str = "pc_test", order_id: str = "ord_1") -> dict:
    return {
        "event_type": EXECUTION_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "candidate_id": "cand_1",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "risk_amount": 2.5,
        "position_size": 0.5,
        "notional": 50.0,
        "submit_result": {"order_id": order_id, "order_submitted": True, "position_opened": True},
        "orders_submitted_by_lsr_v2_submit": 1,
        "positions_opened_by_lsr_v2_submit": 1,
        "broker_submit_called": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def _write_state(data_dir: Path, *, cycle_id: str = "pc_test", order_id: str = "ord_1", position_id: str = "pos_1", extra_position: bool = False) -> None:
    positions = {
        position_id: {
            "position_id": position_id,
            "order_id": order_id,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "entry_price": 100.0,
            "current_price": 103.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "position_size": 0.5,
            "notional": 50.0,
            "risk_amount": 2.5,
            "risk_per_trade_pct": 0.0025,
            "status": "OPEN",
            "open": True,
            "metadata": {
                "cycle_id": cycle_id,
                "paper_order_source": "lsr_v2_supervised_paper_submit_execution",
                "execution_source": "lsr_v2_supervised_paper_submit_execution",
            },
        }
    }
    if extra_position:
        positions["pos_2"] = {**positions[position_id], "position_id": "pos_2", "order_id": "ord_2"}
    _write_json(data_dir / "paper_state.json", {
        "balance": 1000.0,
        "orders": {
            order_id: {
                "order_id": order_id,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "price": 100.0,
                "qty": 0.5,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "status": "FILLED",
                "metadata": {
                    "cycle_id": cycle_id,
                    "paper_order_source": "lsr_v2_supervised_paper_submit_execution",
                },
            }
        },
        "positions": positions,
    })
    _write_json(data_dir / "paper_status.json", {"open_positions": len(positions), "pending_orders": 0})


def _write_execution(data_dir: Path, row: dict) -> None:
    _append_jsonl(data_dir / "lsr_v2_supervised_paper_submit_execution.jsonl", row)
    _write_json(data_dir / "lsr_v2_supervised_paper_submit_execution_report.json", {
        "decision": "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": row["cycle_id"],
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
    })


def test_lifecycle_ready_for_open_position(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    row = _execution_row()
    _write_execution(data_dir, row)
    _write_state(data_dir)

    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["matching_order_count"] == 1
    assert report["matching_position_count"] == 1
    assert report["open_lsr_v2_position_count"] == 1
    assert report["paper_state_consistency"] is True
    assert report["paper_status_consistency"] is True
    assert report["orders_submitted_by_lifecycle_audit"] == 0
    assert report["positions_opened_by_lifecycle_audit"] == 0
    rows = [json.loads(line) for line in (data_dir / "lsr_v2_paper_position_lifecycle.jsonl").read_text().splitlines()]
    assert rows[0]["event_type"] == EVENT_TYPE
    assert rows[0]["risk_multiple_current"] == 0.6


def test_position_not_found_when_execution_exists_but_state_clean(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_execution(data_dir, _execution_row())
    _write_json(data_dir / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(data_dir / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir)

    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert "matching_position_not_found" in report["blockers"]


def test_state_inconsistent_when_status_underreports_positions(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_execution(data_dir, _execution_row())
    _write_state(data_dir)
    _write_json(data_dir / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir)

    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert "paper_status_inconsistent" in report["blockers"]


def test_rejects_duplicate_lsr_positions_over_max(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_execution(data_dir, _execution_row())
    _write_state(data_dir, extra_position=True)

    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir)

    assert report["decision"] == REJECT_DECISION
    assert report["duplicate_position_check"] is False
    assert report["max_positions_check"] is False


def test_missing_execution_stays_diagnostic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_json(data_dir / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(data_dir / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir)

    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["execution_events"] == 0
    assert report["orders_submitted_by_lifecycle_audit"] == 0
