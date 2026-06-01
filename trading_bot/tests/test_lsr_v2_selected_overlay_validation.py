from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_selected_overlay_validation import (
    LSRV2SelectedOverlayValidationSettings,
    READY_DECISION,
    COST_FAILED_DECISION,
    LOSS_STREAK_FAILED_DECISION,
    NO_TRADES_DECISION,
    SELECTED_OVERLAY_ID,
    run_lsr_v2_selected_overlay_validation,
)
from trading_bot.core.lsr_v2_combined_risk_overlay import LOCKED_PROFILE_NAME, LOCKED_VARIANT_ID


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _row(i: int, *, cost_model: str, net_r: float, overlay: bool = False, kept: bool = True, side: str | None = None, symbol: str | None = None) -> dict:
    side = side or ("LONG" if i % 2 == 0 else "SHORT")
    symbol = symbol or ("BTC/USDT" if i % 2 == 0 else "ETH/USDT")
    row = {
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "sample_expansion_symbol": symbol,
        "sample_expansion_timeframe": "5m" if i % 3 else "15m",
        "candidate_id": f"c_{i:04d}",
        "side": side,
        "entry_timestamp": f"2026-01-{(i % 28) + 1:02d}T00:{i % 60:02d}:00Z",
        "entry_index": i,
        "entry_price": 1000.0 + i,
        "stop_loss": 990.0 + i,
        "take_profit": 1020.0 + i,
        "exit_reason": "TP" if net_r > 0 else "SL",
        "cost_model": cost_model,
        "gross_r": net_r + 0.05,
        "cost_r": 0.05,
        "net_r": net_r,
        "window_size": 50000,
    }
    if overlay:
        row.update({
            "event_type": "LSR_V2_COMBINED_RISK_OVERLAY_TRADE",
            "overlay_id": SELECTED_OVERLAY_ID,
            "trade_kept_by_combined_overlay": kept,
            "audit_only": True,
            "promotion_ready": False,
        })
    return row


def _make_dataset(n: int = 24, *, severe_delta: float = 0.10) -> tuple[list[dict], list[dict]]:
    combined: list[dict] = []
    sample: list[dict] = []
    for i in range(n):
        net = 0.55 if i % 5 else -0.30
        p = _row(i, cost_model="conservative", net_r=net, overlay=True)
        s = _row(i, cost_model="severe", net_r=net - severe_delta, overlay=False)
        combined.append(p)
        sample.extend([_row(i, cost_model="conservative", net_r=net, overlay=False), s])
    return combined, sample


def test_no_trades_report_is_safe(tmp_path: Path) -> None:
    report = run_lsr_v2_selected_overlay_validation(
        LSRV2SelectedOverlayValidationSettings(data_dir=str(tmp_path))
    )
    assert report["status"] == "WARN"
    assert report["decision"] == NO_TRADES_DECISION
    assert report["orders_submitted_by_lsr_v2_selected_overlay_validation"] == 0
    assert report["positions_opened_by_lsr_v2_selected_overlay_validation"] == 0
    assert report["promotion_ready"] is False
    assert (tmp_path / "lsr_v2_selected_overlay_validation_report.json").exists()


def test_selected_overlay_validation_can_pass_with_locked_rows(tmp_path: Path) -> None:
    combined, sample = _make_dataset(40, severe_delta=0.05)
    _write_jsonl(tmp_path / "lsr_v2_combined_risk_overlay_trades.jsonl", combined)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", sample)
    report = run_lsr_v2_selected_overlay_validation(
        LSRV2SelectedOverlayValidationSettings(
            data_dir=str(tmp_path),
            min_unique_primary_trades=20,
            bootstrap_iterations=50,
            max_drawdown_r=10.0,
            max_consecutive_losses_limit=5,
            max_asset_pnl_share=0.80,
            max_timeframe_pnl_share=0.80,
        )
    )
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["selected_overlay_id"] == SELECTED_OVERLAY_ID
    assert report["selected_primary_trades"] == 40
    assert report["paired_severe_trades"] == 40
    assert report["walk_forward_stable"] is True
    assert report["oos_pass"] is True
    assert report["bootstrap_pass"] is True
    assert report["cost_degradation_non_destructive"] is True
    assert report["promotion_ready"] is False


def test_wrong_overlay_id_is_not_validated(tmp_path: Path) -> None:
    combined, sample = _make_dataset(12)
    for row in combined:
        row["overlay_id"] = "combo_other"
    _write_jsonl(tmp_path / "lsr_v2_combined_risk_overlay_trades.jsonl", combined)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", sample)
    report = run_lsr_v2_selected_overlay_validation(
        LSRV2SelectedOverlayValidationSettings(data_dir=str(tmp_path), min_unique_primary_trades=5)
    )
    assert report["status"] == "WARN"
    assert report["decision"] == NO_TRADES_DECISION
    assert "no_selected_overlay_primary_trades" in report["blockers"]


def test_cost_degradation_failure_is_reported(tmp_path: Path) -> None:
    combined, sample = _make_dataset(30, severe_delta=1.20)
    _write_jsonl(tmp_path / "lsr_v2_combined_risk_overlay_trades.jsonl", combined)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", sample)
    report = run_lsr_v2_selected_overlay_validation(
        LSRV2SelectedOverlayValidationSettings(
            data_dir=str(tmp_path),
            min_unique_primary_trades=20,
            bootstrap_iterations=50,
            max_drawdown_r=20.0,
            max_consecutive_losses_limit=10,
            max_asset_pnl_share=0.85,
            max_timeframe_pnl_share=0.85,
        )
    )
    assert report["decision"] == COST_FAILED_DECISION
    assert "cost_degradation_failed" in report["blockers"]
    assert report["cost_degradation_non_destructive"] is False


def test_loss_streak_failure_is_reported(tmp_path: Path) -> None:
    combined: list[dict] = []
    sample: list[dict] = []
    for i in range(30):
        net = -0.35 if 5 <= i <= 9 else 0.55
        combined.append(_row(i, cost_model="conservative", net_r=net, overlay=True))
        sample.append(_row(i, cost_model="conservative", net_r=net, overlay=False))
        sample.append(_row(i, cost_model="severe", net_r=net - 0.05, overlay=False))
    _write_jsonl(tmp_path / "lsr_v2_combined_risk_overlay_trades.jsonl", combined)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", sample)
    report = run_lsr_v2_selected_overlay_validation(
        LSRV2SelectedOverlayValidationSettings(
            data_dir=str(tmp_path),
            min_unique_primary_trades=20,
            bootstrap_iterations=50,
            max_drawdown_r=20.0,
            max_consecutive_losses_limit=3,
            max_asset_pnl_share=0.90,
            max_timeframe_pnl_share=0.90,
        )
    )
    assert report["decision"] == LOSS_STREAK_FAILED_DECISION
    assert report["max_consecutive_losses"] == 5
    assert "max_consecutive_losses_above_limit" in report["blockers"]
