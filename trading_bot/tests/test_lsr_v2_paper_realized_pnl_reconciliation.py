from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_realized_pnl_reconciliation import (
    REJECT_DECISION,
    WARN_DECISION,
    calculate_gross_pnl,
    build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files,
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
    side: str = "SELL",
    entry: float = 100.0,
    exit_price: float = 110.0,
    qty: float = 1.0,
    entry_fee: float = 1.0,
    exit_fee: float = 2.0,
    realized: float | None = None,
    final_status: str = "WARN",
) -> Path:
    data = tmp_path / "data"
    cycle = "pc_30_3_0f"
    order_id = "po_test"
    position_id = "pp_test"
    gross = calculate_gross_pnl(side=side, entry_price=entry, exit_price=exit_price, quantity=qty)
    if realized is None:
        realized = gross - exit_fee
    total_fees = entry_fee + exit_fee
    balance_before = 1000.0
    balance_after = balance_before + gross - total_fees
    _write_json(data / "paper_state.json", {
        "balance": balance_after,
        "peak_balance": balance_before,
        "realized_pnl": balance_after - 1000.0,
        "orders": {
            order_id: {
                "order_id": order_id,
                "symbol": "BTC/USDT",
                "side": side,
                "status": "FILLED",
                "filled_price": entry,
                "qty": qty,
                "metadata": {
                    "cycle_id": cycle,
                    "execution_source": "lsr_v2_supervised_paper_submit_execution",
                    "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                    "selected_overlay_id": "combo_loss3_dd10_side_cap",
                },
            }
        },
        "positions": {
            position_id: {
                "position_id": position_id,
                "symbol": "BTC/USDT",
                "side": side,
                "status": "CLOSED",
                "entry_price": entry,
                "exit_price": exit_price,
                "stop_loss": 120.0 if side == "SELL" else 90.0,
                "take_profit": 80.0 if side == "SELL" else 120.0,
                "qty": qty,
                "fees_paid": total_fees,
                "realized_pnl": realized,
                "close_reason": "SL",
                "metadata": {
                    "cycle_id": cycle,
                    "source_order_id": order_id,
                    "risk_amount": abs(gross) if gross else 1.0,
                    "candidate_id": "candidate_test",
                    "execution_source": "lsr_v2_supervised_paper_submit_execution",
                    "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
                    "selected_overlay_id": "combo_loss3_dd10_side_cap",
                },
            }
        },
    })
    _write_json(data / "paper_status.json", {
        "balance": balance_after,
        "equity": balance_after,
        "open_positions": 0,
        "pending_orders": 0,
        "unrealized_pnl": 0.0,
    })
    _write_json(data / "lsr_v2_paper_final_runtime_audit_report.json", {
        "status": final_status,
        "decision": "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_WARN_NON_BLOCKING",
        "final_state": "FLAT",
        "cycle_id": cycle,
        "order_id": order_id,
        "position_id": position_id,
        "safety_flags": {
            "live_mode_enabled": False,
            "testnet_mode_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_real_called": False,
            "broker_close_real_called": False,
        },
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_submit_execution.jsonl", [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": cycle,
        "candidate_id": "candidate_test",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "risk_amount": abs(gross) if gross else 1.0,
        "quality": {"grade": "A"},
    }])
    return data


def test_gross_pnl_sell_formula() -> None:
    assert calculate_gross_pnl(side="SELL", entry_price=100.0, exit_price=110.0, quantity=2.0) == -20.0


def test_gross_pnl_buy_formula() -> None:
    assert calculate_gross_pnl(side="BUY", entry_price=100.0, exit_price=110.0, quantity=2.0) == 20.0


def test_fee_accounting_exit_fee_only_warn_non_blocking(tmp_path: Path) -> None:
    data = _seed(tmp_path, side="SELL")
    bundle = build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(data_dir=data)
    report = bundle["pnl_report"]
    assert report["decision"] == WARN_DECISION
    assert report["fee_accounting_mode"] == "net_includes_exit_fee_only"
    assert report["pnl_includes_fees"] is True
    assert report["pnl_fee_inclusion_scope"] == "exit_fee_only"
    assert report["gross_pnl"] == -10.0
    assert report["realized_pnl_recorded"] == -12.0
    assert report["account_net_pnl_expected"] == -13.0
    assert report["balance_delta"] == -13.0
    assert bundle["postmortem_report"]["should_block_next_order_experimentation"] is False


def test_buy_reconciliation_uses_buy_formula(tmp_path: Path) -> None:
    data = _seed(tmp_path, side="BUY", entry=100.0, exit_price=110.0)
    report = build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(data_dir=data)["pnl_report"]
    assert report["gross_pnl"] == 10.0
    assert report["realized_pnl_recorded"] == 8.0
    assert report["fee_accounting_mode"] == "net_includes_exit_fee_only"


def test_unknown_fee_mode_fails(tmp_path: Path) -> None:
    data = _seed(tmp_path, side="BUY", entry=100.0, exit_price=110.0, entry_fee=1.0, exit_fee=2.0, realized=6.0)
    report = build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(data_dir=data)["pnl_report"]
    assert report["status"] == "FAIL"
    assert report["decision"] == REJECT_DECISION
    assert "fees_paid_internal_mismatch" in report["blockers"]


def test_missing_final_audit_fails(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    (data / "lsr_v2_paper_final_runtime_audit_report.json").unlink()
    report = build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(data_dir=data)["pnl_report"]
    assert report["status"] == "FAIL"
    assert "final_runtime_audit_missing_or_not_ready" in report["blockers"]


def test_reconciliation_does_not_mutate_state_or_status(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    before_state = (data / "paper_state.json").read_text(encoding="utf-8")
    before_status = (data / "paper_status.json").read_text(encoding="utf-8")
    build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(data_dir=data)
    assert (data / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (data / "paper_status.json").read_text(encoding="utf-8") == before_status
