from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_execution_ablation import (
    ENTRY_POLICIES,
    MAX_HOLDING_SET,
    STOP_POLICIES,
    TARGET_POLICIES,
    LSRV2ExecutionAblationSettings,
    build_default_variants,
    parse_windows,
    run_lsr_v2_execution_ablation,
)


def _base_rows(count: int = 20, *, start: int = 0):
    rows = []
    for i in range(count):
        rows.append({
            "timestamp": f"2026-05-28T00:{(start + i) % 60:02d}:00+00:00",
            "open": 102.0,
            "high": 105.0,
            "low": 100.0,
            "close": 102.0,
            "volume": 100.0,
            "market_regime": "RANGING",
        })
    return rows


def _buy_win_rows(start: int = 0):
    rows = _base_rows(20, start=start)
    rows.append({"timestamp": f"2026-05-28T01:{start % 60:02d}:00+00:00", "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 1) % 60:02d}:00+00:00", "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 2) % 60:02d}:00+00:00", "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 3) % 60:02d}:00+00:00", "open": 104.0, "high": 106.5, "low": 103.5, "close": 106.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4))
    return rows


def _buy_loss_rows(start: int = 0):
    rows = _base_rows(20, start=start)
    rows.append({"timestamp": f"2026-05-28T02:{start % 60:02d}:00+00:00", "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 1) % 60:02d}:00+00:00", "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 2) % 60:02d}:00+00:00", "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 3) % 60:02d}:00+00:00", "open": 100.0, "high": 100.2, "low": 98.8, "close": 99.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4))
    return rows


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_default_variant_grid_is_complete():
    variants = build_default_variants()
    assert len(variants) == len(ENTRY_POLICIES) * len(STOP_POLICIES) * len(TARGET_POLICIES) * len(MAX_HOLDING_SET)
    assert len({v.variant_id for v in variants}) == len(variants)
    assert parse_windows("10k, 12000") == (10000, 12000)


def test_execution_ablation_writes_reports_and_trades(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_loss_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)

    report = run_lsr_v2_execution_ablation(LSRV2ExecutionAblationSettings(
        data_dir=str(data_dir),
        timeframe="5m",
        windows=(len(rows),),
        primary_windows=(len(rows),),
        cost_models=("base", "conservative", "severe"),
        min_closed_trades=1,
        min_positive_windows=1,
        min_severe_positive_windows=1,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
        require_severe_cost_survival=False,
    ))

    assert report["status"] == "PASS"
    assert report["input_rows"] == len(rows)
    assert report["timeframe_match"] is True
    assert report["variant_count"] > 0
    assert report["total_trade_rows"] > 0
    assert report["best_variant_id"]
    assert report["orders_submitted_by_lsr_v2_ablation"] == 0
    assert report["positions_opened_by_lsr_v2_ablation"] == 0
    assert report["promotion_ready"] is False
    assert (data_dir / "lsr_v2_execution_ablation_report.json").exists()
    assert (data_dir / "lsr_v2_execution_ablation_variants.json").exists()
    assert (data_dir / "lsr_v2_cost_break_even_report.json").exists()
    trade_lines = (data_dir / "lsr_v2_execution_ablation_trades.jsonl").read_text(encoding="utf-8").splitlines()
    assert trade_lines
    event = json.loads(trade_lines[0])
    assert event["event_type"] == "LSR_V2_EXECUTION_ABLATION_TRADE"
    assert event["submit_order"] is False
    assert event["broker_submit_called"] is False
    assert event["orders_submitted_by_lsr_v2_ablation"] == 0


def test_missing_market_data_is_safe_warn(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = run_lsr_v2_execution_ablation(LSRV2ExecutionAblationSettings(data_dir=str(data_dir), windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
    assert report["orders_submitted_by_lsr_v2_ablation"] == 0
    assert report["positions_opened_by_lsr_v2_ablation"] == 0
    assert (data_dir / "lsr_v2_execution_ablation_report.json").exists()
    assert (data_dir / "lsr_v2_execution_ablation_trades.jsonl").exists()


def test_strict_timeframe_mismatch_is_rejected(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "btc_15m_50k_cache.csv", _buy_win_rows())
    report = run_lsr_v2_execution_ablation(LSRV2ExecutionAblationSettings(data_dir=str(data_dir), timeframe="5m", windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
    assert report["timeframe_match"] is False
    assert report["orders_submitted_by_lsr_v2_ablation"] == 0
    assert report["positions_opened_by_lsr_v2_ablation"] == 0


def test_cost_break_even_report_pairs_primary_and_severe(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_win_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)
    report = run_lsr_v2_execution_ablation(LSRV2ExecutionAblationSettings(
        data_dir=str(data_dir),
        timeframe="5m",
        windows=(len(rows),),
        primary_windows=(len(rows),),
        cost_models=("conservative", "severe"),
        min_closed_trades=1,
        min_positive_windows=1,
        min_severe_positive_windows=1,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
        require_severe_cost_survival=False,
    ))
    cost_report = json.loads(Path(report["cost_break_even_report"]).read_text(encoding="utf-8"))
    assert cost_report["paired_trade_count"] > 0
    assert "avg_slippage_break_even_bps" in cost_report
    assert "avg_maker_vs_taker_difference_r" in cost_report
