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

from core.lsr_v2_backtest_matrix import (
    LSRV2BacktestSettings,
    parse_windows,
    run_lsr_v2_backtest_matrix,
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
    # Next bar reaches TP for the BUY candidate.
    rows.append({"timestamp": f"2026-05-28T01:{(start + 3) % 60:02d}:00+00:00", "open": 104.0, "high": 106.5, "low": 103.5, "close": 106.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4))
    return rows


def _buy_loss_rows(start: int = 0):
    rows = _base_rows(20, start=start)
    rows.append({"timestamp": f"2026-05-28T02:{start % 60:02d}:00+00:00", "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 1) % 60:02d}:00+00:00", "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 2) % 60:02d}:00+00:00", "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    # Next bar reaches SL.
    rows.append({"timestamp": f"2026-05-28T02:{(start + 3) % 60:02d}:00+00:00", "open": 100.0, "high": 100.2, "low": 98.8, "close": 99.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4))
    return rows


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_parse_windows_accepts_k_labels():
    assert parse_windows("10k,12000, 15K") == (10000, 12000, 15000)


def test_backtest_matrix_writes_reports_and_trade_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_loss_rows(30) + _buy_win_rows(60)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)

    report = run_lsr_v2_backtest_matrix(LSRV2BacktestSettings(
        data_dir=str(data_dir),
        timeframe="5m",
        windows=(len(rows),),
        primary_windows=(len(rows),),
        cost_models=("base", "conservative"),
        min_closed_trades=1,
        min_positive_windows=1,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
        max_holding_bars=12,
    ))

    assert report["status"] == "PASS"
    assert report["input_rows"] == len(rows)
    assert report["timeframe_match"] is True
    assert report["total_simulated_trade_rows"] >= 1
    assert report["orders_submitted_by_lsr_v2_backtest"] == 0
    assert report["positions_opened_by_lsr_v2_backtest"] == 0
    assert report["promotion_ready"] is False
    assert (data_dir / "lsr_v2_backtest_matrix_report.json").exists()
    assert (data_dir / "lsr_v2_cost_stress_report.json").exists()
    trade_files = report["trade_files"]
    assert trade_files
    first_file = Path(next(iter(trade_files.values())))
    lines = first_file.read_text(encoding="utf-8").splitlines()
    assert lines
    event = json.loads(lines[0])
    assert event["event_type"] == "LSR_V2_BACKTEST_TRADE"
    assert event["submit_order"] is False
    assert event["broker_submit_called"] is False
    assert event["orders_submitted_by_lsr_v2_backtest"] == 0


def test_missing_market_data_is_safe_warn(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = run_lsr_v2_backtest_matrix(LSRV2BacktestSettings(data_dir=str(data_dir), windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
    assert report["orders_submitted_by_lsr_v2_backtest"] == 0
    assert report["positions_opened_by_lsr_v2_backtest"] == 0
    assert (data_dir / "lsr_v2_backtest_matrix_report.json").exists()
    assert (data_dir / "lsr_v2_cost_stress_report.json").exists()


def test_strict_timeframe_mismatch_is_rejected(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "btc_15m_50k_cache.csv", _buy_win_rows())
    report = run_lsr_v2_backtest_matrix(LSRV2BacktestSettings(data_dir=str(data_dir), timeframe="5m", windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
    assert report["timeframe_match"] is False
    assert report["orders_submitted_by_lsr_v2_backtest"] == 0
    assert report["positions_opened_by_lsr_v2_backtest"] == 0


def test_cost_stress_severe_degrades_results(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_win_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)
    report = run_lsr_v2_backtest_matrix(LSRV2BacktestSettings(
        data_dir=str(data_dir),
        timeframe="5m",
        windows=(len(rows),),
        primary_windows=(len(rows),),
        cost_models=("base", "severe"),
        min_closed_trades=1,
        min_positive_windows=1,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
        max_holding_bars=12,
        require_severe_cost_survival=False,
    ))
    model_summary = report["cost_stress_summary"]
    assert "base" in model_summary
    assert "severe" in model_summary
    assert model_summary["severe"]["weighted_avg_r_post_cost"] <= model_summary["base"]["weighted_avg_r_post_cost"]
