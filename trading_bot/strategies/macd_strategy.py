from __future__ import annotations

import pandas as pd

from trading_bot.strategy_runtime.strategy_signal_schema import condition, make_signal
from trading_bot.strategies.base_strategy import BaseStrategy, atr, column, f, risk_levels


class MacdCrossStrategy(BaseStrategy):
    strategy_id = "macd"
    display_name = "MACD Cross"

    def evaluate(self, df: pd.DataFrame, *, asset: str = "", timeframe: str = "") -> dict:
        if len(df) < 40:
            return self._wait("insufficient_history")
        close = column(df, "Close")
        fast = close.ewm(span=self.params.get_int("fast", 12), adjust=False).mean()
        slow = close.ewm(span=self.params.get_int("slow", 26), adjust=False).mean()
        macd = fast - slow
        signal_line = macd.ewm(span=self.params.get_int("signal", 9), adjust=False).mean()
        prev_macd = f(macd.iloc[-2])
        prev_signal = f(signal_line.iloc[-2])
        last_macd = f(macd.iloc[-1])
        last_signal = f(signal_line.iloc[-1])
        last_close = f(close.iloc[-1])
        bullish_cross = prev_macd <= prev_signal and last_macd > last_signal
        bearish_cross = prev_macd >= prev_signal and last_macd < last_signal
        zero_coherent_buy = bullish_cross and last_macd >= 0
        zero_coherent_sell = bearish_cross and last_macd <= 0
        conds = [
            condition("macd_bullish_cross", bullish_cross, f"{last_macd:.6f}>{last_signal:.6f}", "MACD crossed above signal"),
            condition("macd_bearish_cross", bearish_cross, f"{last_macd:.6f}<{last_signal:.6f}", "MACD crossed below signal"),
            condition("zero_line_coherent", zero_coherent_buy or zero_coherent_sell, f"macd={last_macd:.6f}", "cross direction agrees with zero line"),
        ]
        score = 0.0
        if bullish_cross or bearish_cross:
            score = 60.0
        if zero_coherent_buy or zero_coherent_sell:
            score = 85.0
        signal = "WAIT"
        if bullish_cross:
            signal = "BUY"
        elif bearish_cross:
            signal = "SELL"
        blocked = signal == "WAIT"
        sl, tp = (None, None)
        if signal != "WAIT":
            sl, tp = risk_levels(last_close, f(atr(df).iloc[-1], last_close * 0.01), signal)
        return make_signal(
            strategy=self.strategy_id,
            signal=signal,
            score=score,
            conditions=conds,
            entry_price=last_close if signal != "WAIT" else None,
            sl=sl,
            tp=tp,
            risk_pct=1.0 if signal != "WAIT" else None,
            blocked=blocked,
            block_reasons=["no_macd_cross"] if blocked else [],
        )
