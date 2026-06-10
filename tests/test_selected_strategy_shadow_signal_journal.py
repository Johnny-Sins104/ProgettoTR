from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from trading_bot.dashboard.strategy_dashboard_api import get_strategy_status
from trading_bot.run_selected_strategy_shadow_signal_journal import build_and_write_journal_report
from trading_bot.strategy_runtime.selected_strategy_shadow_diagnostics import build_selected_strategy_shadow_stats
from trading_bot.strategy_runtime.selected_strategy_shadow_journal import journal_path, read_shadow_events
from trading_bot.strategy_runtime.strategy_config_store import save_runtime_config
from trading_bot.strategy_runtime.strategy_signal_executor import execute_shadow_signal


def sample_ohlcv(rows: int = 140) -> pd.DataFrame:
    close = [100 + idx * 0.05 for idx in range(rows)]
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC"),
            "Open": close,
            "High": [value + 0.5 for value in close],
            "Low": [value - 0.5 for value in close],
            "Close": close,
            "Volume": [1000 + idx for idx in range(rows)],
        }
    )


def save_strategy(tmp_path: Path, strategy: str) -> None:
    save_runtime_config(
        tmp_path,
        {
            "active_strategy": strategy,
            "mode": "paper",
            "updated_by": "test",
            "can_trade": False,
            "reason": "selector_read_only_stage",
        },
    )


def write_cache(tmp_path: Path, asset: str, timeframe: str, rows: int = 140) -> None:
    filename = {
        ("XRP/USDT", "5m"): "xrpusdt_5m_150k_cache.parquet",
        ("XRP/USDT", "1m"): "xrpusdt_1m_cache.parquet",
    }[(asset, timeframe)]
    sample_ohlcv(rows).to_parquet(tmp_path / filename, index=False)


def run_with_strategy(tmp_path: Path, strategy: str) -> dict:
    save_strategy(tmp_path, strategy)
    write_cache(tmp_path, "XRP/USDT", "5m")
    return build_and_write_journal_report(data_dir=tmp_path, asset="XRP/USDT", timeframe="5m")


def test_journal_jsonl_created_if_absent(tmp_path: Path):
    assert not journal_path(tmp_path).exists()
    report = run_with_strategy(tmp_path, "ichimoku")
    assert report["status"] == "PASS"
    assert journal_path(tmp_path).exists()


def test_valid_shadow_signal_appended_to_journal(tmp_path: Path):
    run_with_strategy(tmp_path, "ichimoku")
    run_with_strategy(tmp_path, "ichimoku")
    events = read_shadow_events(tmp_path)
    assert len(events) == 2


def test_each_event_has_unique_event_id(tmp_path: Path):
    run_with_strategy(tmp_path, "macd")
    run_with_strategy(tmp_path, "macd")
    ids = [event["event_id"] for event in read_shadow_events(tmp_path)]
    assert len(ids) == len(set(ids))


def test_event_contains_active_strategy_signal_score_conditions_and_blocks(tmp_path: Path):
    run_with_strategy(tmp_path, "bb")
    event = read_shadow_events(tmp_path)[-1]
    assert event["active_strategy"] == "bb"
    assert "signal" in event
    assert "score" in event
    assert isinstance(event["conditions"], list)
    assert isinstance(event["block_reasons"], list)


def test_safety_flags_in_event_remain_false(tmp_path: Path):
    run_with_strategy(tmp_path, "ema_vwap")
    event = read_shadow_events(tmp_path)[-1]
    assert event["shadow_only"] is True
    assert event["would_trade"] is False
    assert event["can_trade"] is False
    assert event["broker_submit_allowed"] is False
    assert event["broker_close_allowed"] is False
    assert event["live_trading_allowed"] is False
    assert event["testnet_allowed"] is False
    assert event["paper_trading_activation_allowed"] is False


def test_ichimoku_saves_only_ichimoku_signal(tmp_path: Path):
    run_with_strategy(tmp_path, "ichimoku")
    assert read_shadow_events(tmp_path)[-1]["active_strategy"] == "ichimoku"


def test_macd_saves_only_macd_signal(tmp_path: Path):
    run_with_strategy(tmp_path, "macd")
    assert read_shadow_events(tmp_path)[-1]["active_strategy"] == "macd"


def test_bb_saves_only_bb_signal(tmp_path: Path):
    run_with_strategy(tmp_path, "bb")
    assert read_shadow_events(tmp_path)[-1]["active_strategy"] == "bb"


def test_ema_vwap_saves_only_ema_signal(tmp_path: Path):
    run_with_strategy(tmp_path, "ema_vwap")
    assert read_shadow_events(tmp_path)[-1]["active_strategy"] == "ema_vwap"


def test_auto_saves_wait_disabled(tmp_path: Path):
    run_with_strategy(tmp_path, "auto")
    event = read_shadow_events(tmp_path)[-1]
    assert event["signal"] == "WAIT"
    assert "auto_strategy_shadow_disabled" in event["block_reasons"]


def test_invalid_strategy_saves_wait_fail_closed(tmp_path: Path):
    (tmp_path / "runtime_strategy_config.json").write_text(json.dumps({"active_strategy": "invalid"}), encoding="utf-8")
    write_cache(tmp_path, "XRP/USDT", "5m")
    report = build_and_write_journal_report(data_dir=tmp_path, asset="XRP/USDT", timeframe="5m")
    event = report["latest_shadow_event"]
    assert event["signal"] == "WAIT"
    assert "invalid_active_strategy" in event["block_reasons"]


def test_insufficient_market_data_saves_wait_fail_closed(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    sample_ohlcv(1).to_parquet(tmp_path / "xrpusdt_5m_150k_cache.parquet", index=False)
    report = build_and_write_journal_report(data_dir=tmp_path, asset="XRP/USDT", timeframe="5m")
    event = report["latest_shadow_event"]
    assert event["signal"] == "WAIT"
    assert "market_data_unavailable" in event["block_reasons"]


def test_paper_state_and_status_not_mutated(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    write_cache(tmp_path, "XRP/USDT", "5m")
    state = tmp_path / "paper_state.json"
    status = tmp_path / "paper_status.json"
    state.write_text('{"sentinel":"state"}', encoding="utf-8")
    status.write_text('{"sentinel":"status"}', encoding="utf-8")
    before_state = state.read_text(encoding="utf-8")
    before_status = status.read_text(encoding="utf-8")
    build_and_write_journal_report(data_dir=tmp_path, asset="XRP/USDT", timeframe="5m")
    assert state.read_text(encoding="utf-8") == before_state
    assert status.read_text(encoding="utf-8") == before_status


def test_outcome_tracker_scaffold_only(tmp_path: Path):
    run_with_strategy(tmp_path, "macd")
    event = read_shadow_events(tmp_path)[-1]
    tracker = event["outcome_tracking"]
    assert tracker["tracking_status"] == "PENDING"
    assert tracker["outcome"] == "UNKNOWN"
    assert tracker["reason"] == "outcome_tracking_scaffold_only"
    assert tracker["would_trade"] is False


def test_aggregated_report_counts_buy_sell_wait(tmp_path: Path):
    events = [
        {"active_strategy": "macd", "signal": "BUY", "score": 80},
        {"active_strategy": "macd", "signal": "SELL", "score": 60},
        {"active_strategy": "macd", "signal": "WAIT", "score": 10},
    ]
    path = journal_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    stats = build_selected_strategy_shadow_stats(tmp_path, strategy="macd")
    assert stats["buy_signals"] == 1
    assert stats["sell_signals"] == 1
    assert stats["wait_signals"] == 1
    assert round(stats["avg_score"], 1) == 50.0


def test_dashboard_status_exposes_latest_event_and_stats(tmp_path: Path):
    run_with_strategy(tmp_path, "ichimoku")
    status = get_strategy_status(data_dir=tmp_path)
    assert status["shadow_journal_available"] is True
    assert status["shadow_events_recorded"] >= 1
    assert status["latest_shadow_event"]["active_strategy"] == "ichimoku"
    assert status["selected_strategy_shadow_stats"]["strategy"] == "ichimoku"
    assert status["outcome_tracking_status"] == "SCAFFOLD_ONLY"


def test_dashboard_status_appends_shadow_event_if_journal_exists_or_not(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    write_cache(tmp_path, "XRP/USDT", "5m")
    assert not journal_path(tmp_path).exists()
    status = get_strategy_status(data_dir=tmp_path)
    assert status["shadow_journal_append_status"] == "OK"
    assert status["shadow_events_recorded"] == 1
    assert read_shadow_events(tmp_path)[-1]["active_strategy"] == "macd"


def test_runtime_config_unreadable_fail_closed_journaled(tmp_path: Path):
    (tmp_path / "runtime_strategy_config.json").write_text("{broken", encoding="utf-8")
    write_cache(tmp_path, "XRP/USDT", "5m")
    report = build_and_write_journal_report(data_dir=tmp_path, asset="XRP/USDT", timeframe="5m")
    assert report["latest_shadow_event"]["signal"] == "WAIT"
    assert "runtime_strategy_config_unreadable" in report["latest_shadow_event"]["block_reasons"]


def test_execute_shadow_signal_still_single_strategy(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    result = execute_shadow_signal(tmp_path, df=sample_ohlcv())
    assert result["evaluated_strategies"] == ["macd"]
    assert result["single_strategy_execution_confirmed"] is True
