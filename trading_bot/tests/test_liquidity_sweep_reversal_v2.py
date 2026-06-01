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

from core.liquidity_sweep_reversal_v2 import (
    EVENT_TYPE,
    LSRV2Settings,
    detect_lsr_v2_candidates,
    run_lsr_v2_candidate_audit,
)


def _base_rows(count: int = 20):
    rows = []
    for i in range(count):
        rows.append({
            "timestamp": f"2026-05-28T00:{i:02d}:00+00:00",
            "open": 102.0,
            "high": 105.0,
            "low": 100.0,
            "close": 102.0,
            "volume": 100.0,
            "market_regime": "RANGING",
        })
    return rows


def _buy_lsr_rows():
    rows = _base_rows(20)
    rows.append({"timestamp": "2026-05-28T00:20:00+00:00", "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": "2026-05-28T00:21:00+00:00", "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": "2026-05-28T00:22:00+00:00", "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8))
    return rows


def _sell_lsr_rows():
    rows = _base_rows(20)
    rows.append({"timestamp": "2026-05-28T00:20:00+00:00", "open": 104.0, "high": 105.60, "low": 103.0, "close": 104.70, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": "2026-05-28T00:21:00+00:00", "open": 104.7, "high": 104.9, "low": 99.0, "close": 99.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": "2026-05-28T00:22:00+00:00", "open": 99.5, "high": 104.95, "low": 99.2, "close": 101.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8))
    return rows


def test_detect_buy_lsr_v2_retest_ready_candidate():
    settings = LSRV2Settings(pool_lookback=20, min_sweep_bps=2.0, retest_tolerance_bps=10.0, max_cost_to_r=0.50)
    candidates = detect_lsr_v2_candidates(_buy_lsr_rows(), settings)
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["event_type"] == EVENT_TYPE
    assert c["side"] == "BUY"
    assert c["archetype"] == "LIQUIDITY_SWEEP_REVERSAL_V2"
    assert c["lifecycle"]["sweep_detected"] is True
    assert c["lifecycle"]["structure_reclaim"] is True
    assert c["lifecycle"]["choch_bos_approx"] is True
    assert c["lifecycle"]["retest_ready"] is True
    assert c["candidate_ready"] is True
    assert c["entry_plan"]["submit_order"] is False
    assert c["entry_plan"]["broker_submit_called"] is False
    assert c["orders_submitted_by_lsr_v2"] == 0
    assert c["positions_opened_by_lsr_v2"] == 0


def test_detect_sell_lsr_v2_candidate():
    settings = LSRV2Settings(pool_lookback=20, min_sweep_bps=2.0, retest_tolerance_bps=10.0, max_cost_to_r=0.50)
    candidates = detect_lsr_v2_candidates(_sell_lsr_rows(), settings)
    assert len(candidates) >= 1
    assert candidates[0]["side"] == "SELL"
    assert candidates[0]["lifecycle"]["retest_ready"] is True
    assert candidates[0]["candidate_ready"] is True


def test_run_lsr_v2_candidate_audit_writes_jsonl_and_report(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "btc_5m_cache.csv"
    rows = _buy_lsr_rows()
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = run_lsr_v2_candidate_audit(LSRV2Settings(data_dir=str(data_dir), pool_lookback=20, retest_tolerance_bps=10.0, max_cost_to_r=0.50))
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_CANDIDATE_AUDIT_READY_DIAGNOSTIC"
    assert report["input_rows"] >= 23
    assert report["candidates_count"] >= 1
    assert report["candidate_ready_count"] >= 1
    assert report["orders_submitted_by_lsr_v2"] == 0
    assert report["positions_opened_by_lsr_v2"] == 0
    assert (data_dir / "lsr_v2_candidate_audit.jsonl").exists()
    assert (data_dir / "lsr_v2_candidate_audit_report.json").exists()
    first_line = (data_dir / "lsr_v2_candidate_audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(first_line)["event_type"] == EVENT_TYPE


def test_missing_market_data_is_safe_warn_without_side_effects(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = run_lsr_v2_candidate_audit(LSRV2Settings(data_dir=str(data_dir)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
    assert report["candidates_count"] == 0
    assert report["orders_submitted_by_lsr_v2"] == 0
    assert report["positions_opened_by_lsr_v2"] == 0
    assert (data_dir / "lsr_v2_candidate_audit.jsonl").exists()


def test_strict_timeframe_rejects_mismatched_market_data(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "btc_15m_50k_cache.csv"
    rows = _buy_lsr_rows()
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = run_lsr_v2_candidate_audit(LSRV2Settings(data_dir=str(data_dir), timeframe="5m"))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
    assert report["requested_timeframe"] == "5m"
    assert report["timeframe_match"] is False
    assert report["candidates_count"] == 0
    assert report["orders_submitted_by_lsr_v2"] == 0
    assert report["positions_opened_by_lsr_v2"] == 0
    assert report["timeframe_mismatch_paths"]
    assert report["timeframe_mismatch_paths"][0]["detected_timeframe"] == "15m"


def test_explicit_timeframe_fallback_records_mismatch_but_runs(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "btc_15m_50k_cache.csv"
    rows = _buy_lsr_rows()
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = run_lsr_v2_candidate_audit(LSRV2Settings(
        data_dir=str(data_dir),
        timeframe="5m",
        allow_timeframe_fallback=True,
        pool_lookback=20,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
    ))
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_CANDIDATE_AUDIT_READY_DIAGNOSTIC"
    assert report["requested_timeframe"] == "5m"
    assert report["detected_timeframe"] == "15m"
    assert report["timeframe_match"] is False
    assert report["allow_timeframe_fallback"] is True
    assert report["candidates_count"] >= 1


def test_quality_report_contains_density_ratios_and_grade_buckets(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "btc_5m_cache.csv"
    rows = _buy_lsr_rows()
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = run_lsr_v2_candidate_audit(LSRV2Settings(data_dir=str(data_dir), timeframe="5m", pool_lookback=20, retest_tolerance_bps=10.0, max_cost_to_r=0.50))
    summary = report["summary"]
    assert report["timeframe_match"] is True
    assert summary["candidate_density_pct"] > 0
    assert summary["ready_density_pct"] > 0
    assert summary["candidate_to_ready_ratio"] > 0
    assert set(summary["quality_buckets"].keys()) >= {"A", "B", "C"}
    assert summary["quality_A"] + summary["quality_B"] + summary["quality_C"] == summary["candidates_count"]
    assert summary["median_rr"] is not None
    first_line = (data_dir / "lsr_v2_candidate_audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
    event = json.loads(first_line)
    assert event["quality"]["grade"] in {"A", "B", "C"}
    assert "sweep_depth_atr" in event["quality"]
