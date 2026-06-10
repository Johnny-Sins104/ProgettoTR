from __future__ import annotations

import pandas as pd

from trading_bot.strategy_runtime.strategy_signal_schema import condition, make_signal
from trading_bot.strategies.base_strategy import BaseStrategy, atr, column, f, risk_levels


class BollingerBandsStrategy(BaseStrategy):
    strategy_id = "bb"
    display_name = "Bollinger Bands"

    def evaluate(self, df: pd.DataFrame, *, asset: str = "", timeframe: str = "") -> dict:
        period = self.params.get_int("bb_period", 20)
        dev = self.params.get_float("bb_dev", 2.0)
        max_width = self.params.get_float("max_band_width_pct", 3.0)
        min_score = self.params.get_float("min_score", 70.0)
        if len(df) < period + 2:
            return self._wait("insufficient_history")
        close = column(df, "Close")
        mid = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = mid + std * dev
        lower = mid - std * dev
        last_close = f(close.iloc[-1])
        prev_close = f(close.iloc[-2])
        last_upper = f(upper.iloc[-1])
        last_lower = f(lower.iloc[-1])
        prev_upper = f(upper.iloc[-2])
        prev_lower = f(lower.iloc[-2])
        last_mid = f(mid.iloc[-1])
        width_pct = (last_upper - last_lower) / last_mid * 100.0 if last_mid else 999.0
        fresh_buy = prev_close >= prev_lower and last_close < last_lower
        fresh_sell = prev_close <= prev_upper and last_close > last_upper
        width_ok = width_pct <= max_width
        ranging_ok = width_ok
        conds = [
            condition("fresh_close_below_lower_band", fresh_buy, f"{last_close:.6f}<{last_lower:.6f}", "fresh lower-band mean reversion trigger"),
            condition("fresh_close_above_upper_band", fresh_sell, f"{last_close:.6f}>{last_upper:.6f}", "fresh upper-band mean reversion trigger"),
            condition("band_width_not_explosive", width_ok, f"{width_pct:.3f}%<= {max_width:.3f}%", "blocks explosive volatility"),
            condition("preferred_regime_ranging", ranging_ok, f"band_width_pct={width_pct:.3f}", "BB is preferred in ranging regimes"),
        ]
        trigger = fresh_buy or fresh_sell
        score = 0.0
        if trigger:
            score += 45.0
        if width_ok:
            score += 35.0
        if ranging_ok:
            score += 20.0
        signal = "WAIT"
        if score >= min_score and width_ok and fresh_buy:
            signal = "BUY"
        elif score >= min_score and width_ok and fresh_sell:
            signal = "SELL"
        block_reasons: list[str] = []
        if not width_ok:
            block_reasons.append("band_width_too_high")
        if not trigger:
            block_reasons.append("no_fresh_bollinger_trigger")
        blocked = signal == "WAIT" or bool(block_reasons)
        atr_value = f(atr(df).iloc[-1], last_close * 0.01)
        sl, tp = (None, None)
        if signal in {"BUY", "SELL"} and not blocked:
            sl, tp = risk_levels(last_close, atr_value, signal)
        return make_signal(
            strategy=self.strategy_id,
            signal=signal if not blocked else "WAIT",
            score=score,
            conditions=conds,
            entry_price=last_close if signal != "WAIT" and not blocked else None,
            sl=sl,
            tp=tp,
            risk_pct=1.0 if signal != "WAIT" and not blocked else None,
            blocked=blocked,
            block_reasons=block_reasons,
        )
