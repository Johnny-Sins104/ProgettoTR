from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.bollinger_strategy import BollingerBandsStrategy
from trading_bot.strategies.ema_vwap_strategy import EmaVwapStrategy
from trading_bot.strategies.ichimoku_strategy import IchimokuStrategy
from trading_bot.strategies.macd_strategy import MacdCrossStrategy


def strategy_factory(strategy: str, params: dict | None = None) -> BaseStrategy:
    normalized = str(strategy or "").strip().lower()
    if normalized == "ema_vwap":
        return EmaVwapStrategy(params)
    if normalized == "bb":
        return BollingerBandsStrategy(params)
    if normalized == "macd":
        return MacdCrossStrategy(params)
    if normalized == "ichimoku":
        return IchimokuStrategy(params)
    raise ValueError(f"unsupported_strategy:{strategy}")


__all__ = [
    "BaseStrategy",
    "BollingerBandsStrategy",
    "EmaVwapStrategy",
    "IchimokuStrategy",
    "MacdCrossStrategy",
    "strategy_factory",
]
