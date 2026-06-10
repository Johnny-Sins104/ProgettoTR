from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from trading_bot.dashboard.strategy_dashboard_api import get_strategy_status, post_strategy_calibrate, post_strategy_select
from trading_bot.run_strategy_selector_dashboard_preflight import build_preflight
from trading_bot.strategies import BollingerBandsStrategy, EmaVwapStrategy, IchimokuStrategy, MacdCrossStrategy
from trading_bot.strategy_runtime.strategy_config_store import (
    load_runtime_config,
    read_position_state,
    runtime_config_path,
    select_strategy,
)
from trading_bot.strategy_runtime.strategy_signal_schema import has_uniform_signal_schema


def sample_ohlcv(rows: int = 120) -> pd.DataFrame:
    base = [100 + idx * 0.02 for idx in range(rows)]
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC"),
            "Open": base,
            "High": [value + 0.4 for value in base],
            "Low": [value - 0.4 for value in base],
            "Close": base,
            "Volume": [1000 + idx for idx in range(rows)],
        }
    )


def test_strategy_selected_valid_saved(tmp_path: Path):
    result = post_strategy_select({"strategy": "bb"}, data_dir=tmp_path)
    assert result["status"] == "OK"
    config = load_runtime_config(tmp_path)
    assert config["active_strategy"] == "bb"
    assert config["can_trade"] is False


def test_strategy_invalid_rejected(tmp_path: Path):
    result = post_strategy_select({"strategy": "not_real"}, data_dir=tmp_path)
    assert result["status"] == "REJECTED"
    assert result["reason"] == "unsupported_strategy"


def test_strategy_switch_blocked_if_position_open(tmp_path: Path):
    def open_reader(_data_dir: Path):
        return {"readable": True, "open_positions": 1}

    result = select_strategy(tmp_path, "macd", position_reader=open_reader)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "open_position_strategy_switch_blocked"


def test_strategy_switch_allowed_if_no_position(tmp_path: Path):
    def flat_reader(_data_dir: Path):
        return {"readable": True, "open_positions": 0}

    result = select_strategy(tmp_path, "macd", position_reader=flat_reader)
    assert result["status"] == "OK"
    assert load_runtime_config(tmp_path)["active_strategy"] == "macd"


def test_runtime_strategy_config_created(tmp_path: Path):
    config = load_runtime_config(tmp_path)
    assert runtime_config_path(tmp_path).exists()
    assert config["active_strategy"] == "bb"
    assert config["reason"] == "selector_read_only_stage"


def test_each_strategy_returns_uniform_signal_schema():
    df = sample_ohlcv()
    strategies = [EmaVwapStrategy(), BollingerBandsStrategy(), MacdCrossStrategy(), IchimokuStrategy()]
    for strategy in strategies:
        signal = strategy.evaluate(df, asset="BTC/USDT", timeframe="5m")
        assert has_uniform_signal_schema(signal), strategy.strategy_id


def test_bb_blocks_trade_if_band_width_too_high():
    df = sample_ohlcv(60)
    df.loc[df.index[-21:-1], "Close"] = [80, 120] * 10
    df.loc[df.index[-2], "Close"] = 100
    df.loc[df.index[-1], "Close"] = 40
    signal = BollingerBandsStrategy({"max_band_width_pct": 0.1}).evaluate(df)
    assert signal["signal"] == "WAIT"
    assert signal["blocked"] is True
    assert "band_width_too_high" in signal["block_reasons"]


def test_ema_uses_real_vwap_when_volumes_available():
    df = sample_ohlcv()
    signal = EmaVwapStrategy().evaluate(df)
    condition_names = {item["name"]: item for item in signal["conditions"]}
    assert "vwap_real_volume_weighted" in condition_names
    assert condition_names["vwap_real_volume_weighted"]["ok"] is True


def test_macd_returns_wait_buy_or_sell_with_coherent_score():
    df = sample_ohlcv()
    signal = MacdCrossStrategy().evaluate(df)
    assert signal["signal"] in {"WAIT", "BUY", "SELL"}
    assert 0 <= signal["score"] <= 100
    if signal["signal"] != "WAIT":
        assert signal["score"] >= 65


def test_ichimoku_wait_if_history_insufficient():
    signal = IchimokuStrategy().evaluate(sample_ohlcv(30))
    assert signal["signal"] == "WAIT"
    assert "insufficient_history" in signal["block_reasons"]


def test_calibration_diagnostic_report_can_trade_false(tmp_path: Path):
    result = post_strategy_calibrate({"strategy": "bb", "asset": "BTC/USDT", "timeframe": "5m"}, data_dir=tmp_path)
    assert result["status"] == "OK"
    report = result["calibration"]
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["can_trade"] is False
    assert Path(report["profile_path"]).exists()


def test_no_broker_submit_close_calls_in_new_modules():
    files = [
        Path("trading_bot/strategy_runtime/strategy_config_store.py"),
        Path("trading_bot/strategy_runtime/strategy_selector.py"),
        Path("trading_bot/strategy_runtime/strategy_calibration_registry.py"),
        Path("trading_bot/dashboard/strategy_dashboard_api.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = ["create_order(", "submit_order(", "broker.submit", ".submit(", "close_position(", "broker.close", ".close_order("]
    assert not any(item in text for item in forbidden)


def test_no_live_testnet_exchange_mutation_in_api_preflight(tmp_path: Path):
    report = build_preflight(tmp_path)
    assert report["paper_trading_activation_allowed"] is False
    assert report["broker_submit_allowed"] is False
    assert report["broker_close_allowed"] is False
    assert report["live_trading_allowed"] is False
    assert report["testnet_allowed"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False


def test_fail_closed_if_position_state_unreadable(tmp_path: Path):
    state = tmp_path / "clean_paper_state.json"
    state.write_text("{broken", encoding="utf-8")
    position = read_position_state(tmp_path)
    assert position["readable"] is False
    result = post_strategy_select({"strategy": "bb"}, data_dir=tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "position_state_unreadable_fail_closed"


def test_strategy_status_endpoint_shape(tmp_path: Path):
    post_strategy_select({"strategy": "ichimoku"}, data_dir=tmp_path)
    status = get_strategy_status(data_dir=tmp_path)
    assert status["status"] == "OK"
    assert status["active_strategy"] == "ichimoku"
    assert status["can_trade"] is False
    assert status["broker_submit_allowed"] is False
