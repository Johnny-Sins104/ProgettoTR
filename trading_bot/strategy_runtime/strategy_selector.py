from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.strategies import strategy_factory
from trading_bot.strategy_runtime.strategy_config_store import load_runtime_config
from trading_bot.strategy_runtime.strategy_signal_schema import wait_signal


def active_strategy(data_dir: Path) -> str:
    return str(load_runtime_config(data_dir).get("active_strategy", "bb"))


def evaluate_active_strategy(
    data_dir: Path,
    df: pd.DataFrame,
    *,
    asset: str = "",
    timeframe: str = "",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = active_strategy(data_dir)
    if selected == "auto":
        return wait_signal("auto", "auto_strategy_disabled_in_preflight")
    strategy = strategy_factory(selected, params)
    return strategy.evaluate(df, asset=asset, timeframe=timeframe)
