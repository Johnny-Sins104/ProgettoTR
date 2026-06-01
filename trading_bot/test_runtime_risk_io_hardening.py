"""Prompt 29.4.4s-1 runtime risk/I/O hardening regression tests."""
from __future__ import annotations

from pathlib import Path
import json
import re
import tempfile

import pandas as pd

from core.jsonl_utils import iter_jsonl_tail
from core.paper_market_data import load_cached_ohlcv, load_replay_ohlcv
from core.portfolio_risk_engine import PortfolioRiskEngine, PortfolioRiskSnapshot


def test_jsonl_tail_reader_does_not_return_entire_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for i in range(20):
                f.write(json.dumps({"event_type": "X", "i": i}) + "\n")
        rows = iter_jsonl_tail(path, max_lines=5, require_event_type=True)
        assert [r["i"] for r in rows] == [15, 16, 17, 18, 19]


def test_local_jsonl_tail_helpers_delegate_to_shared_tail_reader() -> None:
    bad: list[str] = []
    for path in Path("trading_bot/core").glob("*.py"):
        text = path.read_text(encoding="utf-8-sig")
        if "read_text" not in text or "splitlines" not in text:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            match = re.match(r"def\s+(_iter_jsonl_tail|_iter_jsonl_events|_iter_jsonl)\s*\(", line)
            if not match:
                continue
            end = len(lines)
            for scan in range(idx + 1, len(lines)):
                if re.match(r"(def|class)\s+", lines[scan]):
                    end = scan
                    break
            block = "\n".join(lines[idx:end])
            if "read_text" in block and "splitlines" in block:
                bad.append(f"{path}:{idx + 1}:{match.group(1)}")
    assert bad == []


def test_portfolio_var_flag_uses_current_snapshot_not_previous() -> None:
    engine = PortfolioRiskEngine(assets=["BTC"], balance=1000.0, var_limit_pct=0.05)
    exposures = {
        "GLOBAL": {"total_notional": 0.0, "aggregate_leverage": 0.0},
        "BTC": {"weight_pct": 0.0},
    }
    flags = engine._concentration_flags(exposures, engine._safe_corr_matrix(None), portfolio_var=100.0)
    assert "VAR_LIMIT_EXCEEDED" in flags


def test_snapshot_var_flag_ignores_previous_low_var_snapshot() -> None:
    engine = PortfolioRiskEngine(assets=["BTC"], balance=1000.0, var_limit_pct=0.05)
    engine.snapshots.append(PortfolioRiskSnapshot(
        timestamp="old",
        balance=1000.0,
        total_notional=0.0,
        aggregate_leverage=0.0,
        portfolio_var=0.0,
        var_limit=50.0,
        active_positions=0,
        gross_exposure=0.0,
        net_directional_exposure=0.0,
        max_asset_weight_pct=0.0,
        max_pairwise_correlation=0.0,
    ))
    engine.manager.calculate_portfolio_var = lambda weights, returns_df, balance: 100.0

    snapshot = engine.snapshot(current_prices={"BTC": 100.0}, timestamp="current")

    assert snapshot.portfolio_var == 100.0
    assert "VAR_LIMIT_EXCEEDED" in snapshot.concentration_flags


def test_live_exit_fees_use_shared_entry_exit_commission_helper() -> None:
    src = Path("trading_bot/main.py").read_text(encoding="utf-8")
    assert "from core.commission_model import round_trip_commission" in src
    assert "comm_1 = round_trip_commission(size / 2, entry, tp1, COMMISSION_RATE)" in src
    assert "commission = round_trip_commission(size, entry, sl, COMMISSION_RATE)" in src
    assert "comm_2 = round_trip_commission(size / 2, entry, exit_price_2, COMMISSION_RATE)" in src
    assert "comm = round_trip_commission(size, entry, current_price, COMMISSION_RATE)" in src
    assert "comm = round_trip_commission(t[\"size\"], t[\"entry\"], current_price, COMMISSION_RATE)" in src


def test_round_trip_commission_uses_entry_and_exit_notional() -> None:
    from core.commission_model import round_trip_commission

    assert abs(round_trip_commission(0.5, 100.0, 110.0, 0.001) - 0.105) < 1e-12


def test_paper_once_runner_uses_graceful_process_exit_after_teardown() -> None:
    src = Path("trading_bot/run_paper_trading.py").read_text(encoding="utf-8")
    assert "PAPER_ONCE_FORCE_OS_EXIT" in src
    assert "_exit_process(130 if interrupted else 0)" in src
    assert "reason=cycle_completed_watchdog_hard_exit" in src
    assert "os._exit(0)" in src


def test_paper_market_data_cache_normalizes_and_limits_local_ohlcv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        rows = pd.DataFrame({
            "datetime": pd.date_range("2026-01-01", periods=6, freq="5min", tz="UTC"),
            "open": [1, 2, 3, 4, 5, 6],
            "high": [2, 3, 4, 5, 6, 7],
            "low": [0, 1, 2, 3, 4, 5],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            "volume": [10, 11, 12, 13, 14, 15],
        })
        rows.to_parquet(data_dir / "btc_5m_cache.parquet")

        loaded = load_cached_ohlcv(data_dir=data_dir, symbol="BTC/USDT", timeframe="5m", limit=3)

        assert list(loaded.df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(loaded.df) == 3
        assert float(loaded.df.iloc[-1]["Close"]) == 6.5


def test_paper_market_data_replay_advances_offsets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        rows = pd.DataFrame({
            "datetime": pd.date_range("2026-01-01", periods=8, freq="5min", tz="UTC"),
            "Open": range(8),
            "High": range(1, 9),
            "Low": range(8),
            "Close": range(10, 18),
            "Volume": range(20, 28),
        })
        rows.to_parquet(data_dir / "btc_5m_cache.parquet")
        offsets: dict[str, int] = {}

        first = load_replay_ohlcv(data_dir=data_dir, symbol="BTC/USDT", timeframe="5m", limit=4, replay_offsets=offsets)
        second = load_replay_ohlcv(data_dir=data_dir, symbol="BTC/USDT", timeframe="5m", limit=4, replay_offsets=offsets)

        assert first.replay_end_offset == 4
        assert second.replay_end_offset == 5
        assert float(first.df.iloc[-1]["Close"]) == 13.0
        assert float(second.df.iloc[-1]["Close"]) == 14.0


def test_paper_market_data_replay_start_offset_is_honored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        rows = pd.DataFrame({
            "datetime": pd.date_range("2026-01-01", periods=10, freq="5min", tz="UTC"),
            "Open": range(10),
            "High": range(1, 11),
            "Low": range(10),
            "Close": range(100, 110),
            "Volume": range(20, 30),
        })
        rows.to_parquet(data_dir / "btc_5m_cache.parquet")
        offsets: dict[str, int] = {}

        loaded = load_replay_ohlcv(
            data_dir=data_dir,
            symbol="BTC/USDT",
            timeframe="5m",
            limit=4,
            replay_offsets=offsets,
            start_offset=7,
        )

        assert loaded.replay_end_offset == 7
        assert float(loaded.df.iloc[-1]["Close"]) == 106.0


def test_paper_runner_exposes_cache_and_replay_market_data_modes() -> None:
    runner = Path("trading_bot/run_paper_trading.py").read_text(encoding="utf-8")
    engine = Path("trading_bot/core/paper_engine.py").read_text(encoding="utf-8")
    assert '--market-data-mode", choices=["live", "auto", "cache", "replay"]' in runner
    assert "MARKET_DATA_LIVE_FAILED_FALLBACK" in engine
    assert "MARKET_DATA_CACHE_USED" in engine
    assert "load_replay_ohlcv" in engine
    assert "--max-cycles" in runner
    assert "--market-data-replay-start-offset" in runner
    assert "MAX_CYCLES_REACHED" in engine
    assert "--no-cycle-artifacts" in runner
    assert "CYCLE_ARTIFACTS_SKIPPED" in engine


if __name__ == "__main__":
    test_jsonl_tail_reader_does_not_return_entire_file()
    test_local_jsonl_tail_helpers_delegate_to_shared_tail_reader()
    test_portfolio_var_flag_uses_current_snapshot_not_previous()
    test_snapshot_var_flag_ignores_previous_low_var_snapshot()
    test_live_exit_fees_use_shared_entry_exit_commission_helper()
    test_round_trip_commission_uses_entry_and_exit_notional()
    test_paper_once_runner_uses_graceful_process_exit_after_teardown()
    test_paper_market_data_cache_normalizes_and_limits_local_ohlcv()
    test_paper_market_data_replay_advances_offsets()
    test_paper_market_data_replay_start_offset_is_honored()
    test_paper_runner_exposes_cache_and_replay_market_data_modes()
    print("Runtime risk/I/O hardening tests passed.")
