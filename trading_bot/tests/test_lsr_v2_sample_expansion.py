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

from core.lsr_v2_sample_expansion import (
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2SampleExpansionSettings,
    discover_market_inputs,
    parse_symbols,
    parse_timeframes,
    run_lsr_v2_sample_expansion,
)


def _base_rows(count: int = 20, *, start: int = 0, symbol: str = "BTC/USDT"):
    rows = []
    for i in range(count):
        rows.append({
            "timestamp": f"2026-05-28T00:{(start + i) % 60:02d}:00+00:00",
            "symbol": symbol,
            "open": 102.0,
            "high": 105.0,
            "low": 100.0,
            "close": 102.0,
            "volume": 100.0,
            "market_regime": "RANGING",
        })
    return rows


def _buy_win_rows(start: int = 0, *, symbol: str = "BTC/USDT"):
    rows = _base_rows(20, start=start, symbol=symbol)
    rows.append({"timestamp": f"2026-05-28T01:{start % 60:02d}:00+00:00", "symbol": symbol, "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 1) % 60:02d}:00+00:00", "symbol": symbol, "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 2) % 60:02d}:00+00:00", "symbol": symbol, "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T01:{(start + 3) % 60:02d}:00+00:00", "symbol": symbol, "open": 104.0, "high": 106.5, "low": 103.5, "close": 106.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4, symbol=symbol))
    return rows


def _buy_loss_rows(start: int = 0, *, symbol: str = "BTC/USDT"):
    rows = _base_rows(20, start=start, symbol=symbol)
    rows.append({"timestamp": f"2026-05-28T02:{start % 60:02d}:00+00:00", "symbol": symbol, "open": 101.0, "high": 102.0, "low": 99.50, "close": 100.40, "volume": 140.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 1) % 60:02d}:00+00:00", "symbol": symbol, "open": 100.4, "high": 106.0, "low": 100.2, "close": 105.50, "volume": 130.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 2) % 60:02d}:00+00:00", "symbol": symbol, "open": 105.5, "high": 106.2, "low": 100.05, "close": 104.00, "volume": 120.0, "market_regime": "RANGING"})
    rows.append({"timestamp": f"2026-05-28T02:{(start + 3) % 60:02d}:00+00:00", "symbol": symbol, "open": 100.0, "high": 100.2, "low": 98.8, "close": 99.0, "volume": 110.0, "market_regime": "RANGING"})
    rows.extend(_base_rows(8, start=start + 4, symbol=symbol))
    return rows


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_parse_helpers_are_stable():
    assert parse_symbols("BTC/USDT, ETH/USDT, BTC/USDT") == ("BTC/USDT", "ETH/USDT")
    assert parse_timeframes("5min,15m,5m") == ("5m", "15m")


def test_discovery_filters_requested_timeframe(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "btc_5m_cache.csv", _buy_win_rows())
    _write_csv(data_dir / "btc_15m_cache.csv", _buy_win_rows())
    settings = LSRV2SampleExpansionSettings(data_dir=str(data_dir), symbols=("BTC/USDT",), timeframes=("5m",))
    targets, discovery = discover_market_inputs(settings)
    assert len(targets) == 1
    assert targets[0]["timeframe"] == "5m"
    assert discovery["included_count"] == 1
    assert any(x["detected_timeframe"] == "15m" for x in discovery["excluded"])


def test_sample_expansion_writes_reports_and_trades(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = _buy_win_rows(0) + _buy_loss_rows(40) + _buy_win_rows(80)
    _write_csv(data_dir / "btc_5m_cache.csv", rows)

    report = run_lsr_v2_sample_expansion(LSRV2SampleExpansionSettings(
        data_dir=str(data_dir),
        symbols=("BTC/USDT",),
        timeframes=("5m",),
        windows=(len(rows),),
        cost_models=("conservative", "severe"),
        min_closed_trades=1,
        preferred_closed_trades=1,
        min_positive_windows=1,
        min_severe_positive_windows=0,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
    ))

    assert report["status"] == "PASS"
    assert report["locked_profile_name"] == LOCKED_PROFILE_NAME
    assert report["locked_variant_id"] == LOCKED_VARIANT_ID
    assert report["datasets_analyzed"] == 1
    assert report["closed_trades"] > 0
    assert report["orders_submitted_by_lsr_v2_sample_expansion"] == 0
    assert report["positions_opened_by_lsr_v2_sample_expansion"] == 0
    assert report["promotion_ready"] is False
    assert (data_dir / "lsr_v2_sample_expansion_report.json").exists()
    assert (data_dir / "lsr_v2_sample_expansion_by_asset.json").exists()
    assert (data_dir / "lsr_v2_sample_expansion_by_timeframe.json").exists()
    trade_lines = (data_dir / "lsr_v2_sample_expansion_trades.jsonl").read_text(encoding="utf-8").splitlines()
    assert trade_lines
    event = json.loads(trade_lines[0])
    assert event["event_type"] == "LSR_V2_SAMPLE_EXPANSION_TRADE"
    assert event["submit_order"] is False
    assert event["broker_submit_called"] is False


def test_sample_expansion_groups_assets_and_timeframes(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_csv(data_dir / "btc_5m_cache.csv", _buy_win_rows(0, symbol="BTC/USDT") + _buy_win_rows(40, symbol="BTC/USDT"))
    _write_csv(data_dir / "eth_5m_cache.csv", _buy_win_rows(0, symbol="ETH/USDT") + _buy_loss_rows(40, symbol="ETH/USDT"))

    report = run_lsr_v2_sample_expansion(LSRV2SampleExpansionSettings(
        data_dir=str(data_dir),
        symbols=("BTC/USDT", "ETH/USDT"),
        timeframes=("5m",),
        windows=(60,),
        cost_models=("conservative",),
        min_closed_trades=1,
        min_positive_windows=1,
        min_severe_positive_windows=0,
        retest_tolerance_bps=10.0,
        max_cost_to_r=0.50,
    ))
    assert report["datasets_analyzed"] == 2
    assert report["asset_count_with_trades"] >= 1
    by_asset = json.loads((data_dir / "lsr_v2_sample_expansion_by_asset.json").read_text(encoding="utf-8"))
    assert len(by_asset["assets"]) >= 1
    by_tf = json.loads((data_dir / "lsr_v2_sample_expansion_by_timeframe.json").read_text(encoding="utf-8"))
    assert by_tf["timeframes"]


def test_missing_market_data_is_safe_warn(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = run_lsr_v2_sample_expansion(LSRV2SampleExpansionSettings(data_dir=str(data_dir), symbols=("BTC/USDT",), timeframes=("5m",), windows=(40,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
    assert report["orders_submitted_by_lsr_v2_sample_expansion"] == 0
    assert report["positions_opened_by_lsr_v2_sample_expansion"] == 0
    assert (data_dir / "lsr_v2_sample_expansion_report.json").exists()
    assert (data_dir / "lsr_v2_sample_expansion_trades.jsonl").exists()
