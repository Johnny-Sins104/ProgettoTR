from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

from trading_bot.run_strategy_selector_shadow_signal_execution import build_runner_report
from trading_bot.strategies.bollinger_strategy import BollingerBandsStrategy
from trading_bot.strategies.ema_vwap_strategy import EmaVwapStrategy
from trading_bot.strategies.ichimoku_strategy import IchimokuStrategy
from trading_bot.strategies.macd_strategy import MacdCrossStrategy
from trading_bot.strategy_runtime.strategy_config_store import save_runtime_config
from trading_bot.strategy_runtime.strategy_shadow_report import build_and_write_shadow_report
from trading_bot.strategy_runtime.strategy_signal_executor import execute_shadow_signal
from trading_bot.strategy_runtime.strategy_signal_schema import has_uniform_signal_schema, make_signal


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


class SpyStrategy:
    def __init__(self, strategy: str):
        self.strategy = strategy

    def evaluate(self, df, *, asset="", timeframe=""):
        return make_signal(strategy=self.strategy, signal="WAIT", score=7, blocked=True, block_reasons=["spy_wait"])


def spy_factory(calls: list[str]):
    def factory(strategy: str, params=None):
        calls.append(strategy)
        return SpyStrategy(strategy)

    return factory


def test_executor_reads_active_strategy_from_runtime_config(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    report = execute_shadow_signal(tmp_path, df=sample_ohlcv())
    assert report["active_strategy"] == "macd"
    assert report["signal"]["strategy"] == "macd"


def test_active_macd_calculates_only_macd(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    calls: list[str] = []
    execute_shadow_signal(tmp_path, df=sample_ohlcv(), strategy_factory_fn=spy_factory(calls))
    assert calls == ["macd"]


def test_active_bb_calculates_only_bb(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    calls: list[str] = []
    execute_shadow_signal(tmp_path, df=sample_ohlcv(), strategy_factory_fn=spy_factory(calls))
    assert calls == ["bb"]


def test_active_ema_vwap_calculates_only_ema_vwap(tmp_path: Path):
    save_strategy(tmp_path, "ema_vwap")
    calls: list[str] = []
    execute_shadow_signal(tmp_path, df=sample_ohlcv(), strategy_factory_fn=spy_factory(calls))
    assert calls == ["ema_vwap"]


def test_active_ichimoku_calculates_only_ichimoku(tmp_path: Path):
    save_strategy(tmp_path, "ichimoku")
    calls: list[str] = []
    execute_shadow_signal(tmp_path, df=sample_ohlcv(), strategy_factory_fn=spy_factory(calls))
    assert calls == ["ichimoku"]


def test_auto_returns_wait_disabled(tmp_path: Path):
    save_strategy(tmp_path, "auto")
    report = execute_shadow_signal(tmp_path, df=sample_ohlcv())
    assert report["signal"]["signal"] == "WAIT"
    assert "auto_strategy_shadow_disabled" in report["signal"]["block_reasons"]


def test_invalid_strategy_returns_wait_fail_closed(tmp_path: Path):
    (tmp_path / "runtime_strategy_config.json").write_text(json.dumps({"active_strategy": "not_real"}), encoding="utf-8")
    report = execute_shadow_signal(tmp_path, df=sample_ohlcv())
    assert report["signal"]["signal"] == "WAIT"
    assert "invalid_active_strategy" in report["signal"]["block_reasons"]
    assert report["signal"]["would_trade"] is False


def test_insufficient_data_returns_wait_fail_closed(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    report = execute_shadow_signal(tmp_path, df=sample_ohlcv(1))
    assert report["signal"]["signal"] == "WAIT"
    assert "market_data_unavailable" in report["signal"]["block_reasons"]


def test_each_strategy_returns_uniform_shadow_signal_schema():
    df = sample_ohlcv()
    for strategy in [EmaVwapStrategy(), BollingerBandsStrategy(), MacdCrossStrategy(), IchimokuStrategy()]:
        signal = strategy.evaluate(df)
        assert has_uniform_signal_schema(signal), strategy.strategy_id


def test_bb_blocks_with_band_width_too_high():
    df = sample_ohlcv(60)
    df.loc[df.index[-21:-1], "Close"] = [80, 120] * 10
    df.loc[df.index[-2], "Close"] = 100
    df.loc[df.index[-1], "Close"] = 40
    signal = BollingerBandsStrategy({"max_band_width_pct": 0.1}).evaluate(df)
    assert signal["signal"] == "WAIT"
    assert "band_width_too_high" in signal["block_reasons"]


def test_macd_score_85_when_cross_zero_line_coherent():
    random.seed(0)
    price = 100.0
    closes = []
    for idx in range(40):
        price += random.gauss(0, 1) + (0.05 if idx < 25 else -0.02)
        closes.append(price)
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 0.5 for value in closes],
            "Low": [value - 0.5 for value in closes],
            "Close": closes,
            "Volume": [1000] * len(closes),
        }
    )
    signal = MacdCrossStrategy().evaluate(df)
    assert signal["signal"] == "SELL"
    assert signal["score"] == 85.0


def test_ichimoku_insufficient_history():
    signal = IchimokuStrategy().evaluate(sample_ohlcv(30))
    assert signal["signal"] == "WAIT"
    assert "insufficient_history" in signal["block_reasons"]


def test_ema_uses_real_vwap_when_volume_available():
    signal = EmaVwapStrategy().evaluate(sample_ohlcv())
    by_name = {item["name"]: item for item in signal["conditions"]}
    assert by_name["vwap_real_volume_weighted"]["ok"] is True


def test_would_trade_false_even_if_signal_buy_or_sell(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    df = sample_ohlcv(40)
    df.loc[df.index[-25:-1], "Close"] = 100
    df.loc[df.index[-2], "Close"] = 100
    df.loc[df.index[-1], "Close"] = 98
    report = execute_shadow_signal(tmp_path, df=df)
    assert report["signal"]["signal"] in {"BUY", "SELL", "WAIT"}
    assert report["signal"]["would_trade"] is False
    assert report["signal"]["can_trade"] is False
    assert "shadow_signal_execution_only" in report["signal"]["block_reasons"]


def test_safety_flags_remain_false(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    report = build_and_write_shadow_report(data_dir=tmp_path, df=sample_ohlcv())
    assert report["paper_trading_activation_allowed"] is False
    assert report["broker_submit_allowed"] is False
    assert report["broker_close_allowed"] is False
    assert report["live_trading_allowed"] is False
    assert report["testnet_allowed"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False


def test_paper_state_and_status_not_mutated(tmp_path: Path):
    save_strategy(tmp_path, "bb")
    paper_state = tmp_path / "paper_state.json"
    paper_status = tmp_path / "paper_status.json"
    paper_state.write_text('{"sentinel":"state"}', encoding="utf-8")
    paper_status.write_text('{"sentinel":"status"}', encoding="utf-8")
    before_state = paper_state.read_text(encoding="utf-8")
    before_status = paper_status.read_text(encoding="utf-8")
    build_and_write_shadow_report(data_dir=tmp_path, df=sample_ohlcv())
    assert paper_state.read_text(encoding="utf-8") == before_state
    assert paper_status.read_text(encoding="utf-8") == before_status


def test_runner_report_pass_and_shadow_only(tmp_path: Path):
    save_strategy(tmp_path, "macd")
    report = build_runner_report(data_dir=tmp_path, asset="MISSING/USDT")
    assert report["status"] == "PASS"
    assert report["decision"] == "STRATEGY_SELECTOR_SHADOW_SIGNAL_EXECUTION_READY"
    assert report["shadow_only"] is True
    assert report["single_strategy_execution_confirmed"] is True
    assert report["broker_submit_allowed"] is False
