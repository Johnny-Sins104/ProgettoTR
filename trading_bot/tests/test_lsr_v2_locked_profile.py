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

from core.lsr_v2_locked_profile import (
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2LockedProfileSettings,
    locked_variant,
    run_lsr_v2_locked_profile,
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


def test_locked_variant_identity():
    variant = locked_variant()
    assert LOCKED_PROFILE_NAME == "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    assert variant.variant_id == LOCKED_VARIANT_ID
    assert variant.entry_policy == "retest_entry_limit_like"
    assert variant.stop_policy == "stop_at_sweep_extreme"
    assert variant.target_policy == "tp_fixed_2R"
    assert variant.max_holding_bars == 24


def test_locked_profile_writes_drilldown_reports(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_loss_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)

    report = run_lsr_v2_locked_profile(LSRV2LockedProfileSettings(
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

    assert report["status"] == "PASS"
    assert report["locked_profile_name"] == LOCKED_PROFILE_NAME
    assert report["locked_variant_id"] == LOCKED_VARIANT_ID
    assert report["input_rows"] == len(rows)
    assert report["timeframe_match"] is True
    assert report["total_trade_rows"] > 0
    assert report["primary_closed_trades"] > 0
    assert report["orders_submitted_by_lsr_v2_locked_profile"] == 0
    assert report["positions_opened_by_lsr_v2_locked_profile"] == 0
    assert report["promotion_ready"] is False
    assert (data_dir / "lsr_v2_locked_profile_report.json").exists()
    assert (data_dir / "lsr_v2_locked_profile_cost_drilldown.json").exists()
    assert (data_dir / "lsr_v2_locked_profile_window_stability.json").exists()
    trade_lines = (data_dir / "lsr_v2_locked_profile_trades.jsonl").read_text(encoding="utf-8").splitlines()
    assert trade_lines
    event = json.loads(trade_lines[0])
    assert event["event_type"] == "LSR_V2_LOCKED_PROFILE_TRADE"
    assert event["locked_profile_name"] == LOCKED_PROFILE_NAME
    assert event["submit_order"] is False
    assert event["broker_submit_called"] is False


def test_cost_drilldown_pairs_primary_and_severe(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_win_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)

    report = run_lsr_v2_locked_profile(LSRV2LockedProfileSettings(
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
    cost_report = json.loads(Path(report["cost_drilldown_report"]).read_text(encoding="utf-8"))
    assert cost_report["paired_trade_count"] > 0
    assert "primary_win_to_severe_nonwin_ratio" in cost_report
    assert "avg_slippage_break_even_bps" in cost_report
    assert cost_report["orders_submitted_by_lsr_v2_locked_profile_cost_drilldown"] == 0


def test_missing_market_data_is_safe_warn(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = run_lsr_v2_locked_profile(LSRV2LockedProfileSettings(data_dir=str(data_dir), windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
    assert report["orders_submitted_by_lsr_v2_locked_profile"] == 0
    assert report["positions_opened_by_lsr_v2_locked_profile"] == 0
    assert (data_dir / "lsr_v2_locked_profile_report.json").exists()
    assert (data_dir / "lsr_v2_locked_profile_trades.jsonl").exists()


def test_strict_timeframe_mismatch_is_rejected(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "btc_15m_50k_cache.csv", _buy_win_rows())
    report = run_lsr_v2_locked_profile(LSRV2LockedProfileSettings(data_dir=str(data_dir), timeframe="5m", windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
    assert report["timeframe_match"] is False
    assert report["orders_submitted_by_lsr_v2_locked_profile"] == 0
    assert report["positions_opened_by_lsr_v2_locked_profile"] == 0
