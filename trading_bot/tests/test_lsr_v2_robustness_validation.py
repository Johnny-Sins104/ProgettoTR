from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_robustness_validation import (
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2RobustnessValidationSettings,
    run_lsr_v2_robustness_validation,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _trade(i: int, *, cost_model: str = "conservative", net_r: float = 0.30, symbol: str = "BTC/USDT", timeframe: str = "5m", side: str = "BUY", window_size: int = 50000) -> dict:
    gross_r = net_r + (0.05 if cost_model == "conservative" else 0.15)
    return {
        "event_type": "LSR_V2_SAMPLE_EXPANSION_TRADE",
        "prompt_id": "29.4.4s-7e",
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "variant_id": LOCKED_VARIANT_ID,
        "sample_expansion_symbol": symbol,
        "sample_expansion_timeframe": timeframe,
        "symbol": symbol,
        "timeframe": timeframe,
        "candidate_id": f"cand_{i:04d}",
        "side": side,
        "window_size": window_size,
        "window_label": f"{window_size // 1000}k",
        "cost_model": cost_model,
        "entry_index": i * 10,
        "exit_index": i * 10 + 5,
        "entry_timestamp": f"2026-01-01T{(i // 60):02d}:{(i % 60):02d}:00Z",
        "entry_price": 100.0 + i,
        "stop_loss": 99.0 + i,
        "take_profit": 102.0 + i,
        "exit_price": 101.0 + i,
        "exit_reason": "TAKE_PROFIT" if net_r > 0 else "STOP_LOSS",
        "gross_r": round(gross_r, 8),
        "cost_r": round(gross_r - net_r, 8),
        "net_r": round(net_r, 8),
        "orders_submitted_by_lsr_v2_sample_expansion": 0,
        "positions_opened_by_lsr_v2_sample_expansion": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
    }


def _balanced_rows(count: int = 96, *, severe_net: float = 0.12, tail_negative: bool = False) -> list[dict]:
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    tfs = ["5m", "15m"]
    sides = ["BUY", "SELL"]
    rows: list[dict] = []
    for i in range(count):
        net = 0.35
        if tail_negative and i >= int(count * 0.80):
            net = -0.45
        symbol = symbols[i % len(symbols)]
        timeframe = tfs[(i // len(symbols)) % len(tfs)]
        side = sides[i % len(sides)]
        rows.append(_trade(i, cost_model="conservative", net_r=net, symbol=symbol, timeframe=timeframe, side=side))
        rows.append(_trade(i, cost_model="severe", net_r=severe_net if not tail_negative or i < int(count * 0.80) else -0.65, symbol=symbol, timeframe=timeframe, side=side))
    return rows


def test_no_trade_rows_returns_warn(tmp_path: Path):
    report = run_lsr_v2_robustness_validation(LSRV2RobustnessValidationSettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_NO_TRADES"
    assert report["orders_submitted_by_lsr_v2_robustness"] == 0
    assert report["positions_opened_by_lsr_v2_robustness"] == 0
    assert Path(report["report"]).exists()


def test_robust_balanced_fixture_is_ready_for_promotion_gate_review(tmp_path: Path):
    path = tmp_path / "lsr_v2_sample_expansion_trades.jsonl"
    _write_jsonl(path, _balanced_rows(96, severe_net=0.14))
    report = run_lsr_v2_robustness_validation(
        LSRV2RobustnessValidationSettings(data_dir=str(tmp_path), bootstrap_iterations=80, random_seed=1)
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_READY_FOR_PROMOTION_GATE"
    assert report["unique_primary_trades"] == 96
    assert report["walk_forward_stable"] is True
    assert report["oos_pass"] is True
    assert report["bootstrap_pass"] is True
    assert report["cost_degradation_non_destructive"] is True
    assert report["promotion_ready"] is False
    assert Path(report["walk_forward_report"]).exists()
    assert Path(report["oos_report"]).exists()
    assert Path(report["bootstrap_report"]).exists()
    assert Path(report["walk_forward_trades_jsonl"]).exists()


def test_deduplicates_repeated_window_representations(tmp_path: Path):
    rows = []
    for row in _balanced_rows(60, severe_net=0.14):
        rows.append(row)
        dup = dict(row)
        dup["window_size"] = 150000
        dup["window_label"] = "150k"
        rows.append(dup)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", rows)
    report = run_lsr_v2_robustness_validation(
        LSRV2RobustnessValidationSettings(data_dir=str(tmp_path), bootstrap_iterations=40, random_seed=2)
    )
    assert report["primary_raw_trade_rows"] == 120
    assert report["unique_primary_trades"] == 60
    assert report["dedupe_removed_primary_rows"] == 60


def test_oos_failure_is_classified_without_submitting_orders(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _balanced_rows(100, severe_net=0.10, tail_negative=True))
    report = run_lsr_v2_robustness_validation(
        LSRV2RobustnessValidationSettings(data_dir=str(tmp_path), bootstrap_iterations=60, random_seed=3, max_asset_pnl_share=0.90)
    )
    assert "oos_failed" in report["blockers"]
    assert report["oos_pass"] is False
    assert report["orders_submitted_by_lsr_v2_robustness"] == 0
    assert report["positions_opened_by_lsr_v2_robustness"] == 0


def test_cost_degradation_failure_is_classified(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _balanced_rows(80, severe_net=-0.20))
    report = run_lsr_v2_robustness_validation(
        LSRV2RobustnessValidationSettings(data_dir=str(tmp_path), bootstrap_iterations=60, random_seed=4)
    )
    assert "cost_degradation_failed" in report["blockers"]
    assert report["cost_degradation_non_destructive"] is False
    assert report["decision"] in {
        "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_FAILED",
        "KEEP_DIAGNOSTIC_LSR_V2_BOOTSTRAP_FRAGILE",
        "KEEP_DIAGNOSTIC_LSR_V2_WALK_FORWARD_UNSTABLE",
    }
