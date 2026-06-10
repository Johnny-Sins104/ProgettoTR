from __future__ import annotations

import pandas as pd

from trading_bot.strategy_runtime.strategy_signal_schema import condition, make_signal
from trading_bot.strategies.base_strategy import BaseStrategy, atr, column, f, real_vwap, risk_levels, rsi


class EmaVwapStrategy(BaseStrategy):
    strategy_id = "ema_vwap"
    display_name = "EMA + RSI + VWAP"

    def evaluate(self, df: pd.DataFrame, *, asset: str = "", timeframe: str = "") -> dict:
        min_rows = max(self.params.get_int("slow_ema", 50), self.params.get_int("rsi_period", 14)) + 5
        if len(df) < min_rows:
            return self._wait("insufficient_history")
        try:
            close = column(df, "Close")
        except Exception as exc:
            return self._wait(str(exc))
        try:
            volume = column(df, "Volume")
            volume_available = bool(volume.fillna(0).gt(0).any())
        except Exception:
            volume = pd.Series([1.0] * len(df), index=df.index)
            volume_available = False
        fast = self.params.get_int("fast_ema", 20)
        slow = self.params.get_int("slow_ema", 50)
        rsi_period = self.params.get_int("rsi_period", 14)
        min_score = self.params.get_float("min_score", 70.0)
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        rsi_value = rsi(df, rsi_period)
        if volume_available:
            vwap = real_vwap(df)
            vwap_reason = "VWAP uses price weighted by real volume"
        else:
            typical = (column(df, "High") + column(df, "Low") + close) / 3.0
            vwap = typical.rolling(20).mean()
            vwap_reason = "VWAP fallback used because volume is unavailable"
        atr_value = atr(df).iloc[-1]
        last_close = f(close.iloc[-1])
        last_volume = f(volume.iloc[-1])
        last_fast = f(ema_fast.iloc[-1])
        last_slow = f(ema_slow.iloc[-1])
        last_rsi = f(rsi_value.iloc[-1], 50.0)
        last_vwap = f(vwap.iloc[-1])
        bullish = last_fast > last_slow and last_close > last_vwap and 50.0 <= last_rsi <= 72.0
        bearish = last_fast < last_slow and last_close < last_vwap and 28.0 <= last_rsi <= 50.0
        conds = [
            condition("ema_fast_above_slow", last_fast > last_slow, f"{last_fast:.6f}>{last_slow:.6f}", "trend momentum"),
            condition("ema_fast_below_slow", last_fast < last_slow, f"{last_fast:.6f}<{last_slow:.6f}", "bearish trend momentum"),
            condition("close_above_vwap", last_close > last_vwap, f"{last_close:.6f}>{last_vwap:.6f}", "volume-weighted confirmation"),
            condition("close_below_vwap", last_close < last_vwap, f"{last_close:.6f}<{last_vwap:.6f}", "bearish volume-weighted confirmation"),
            condition("rsi_momentum_ok", 50.0 <= last_rsi <= 72.0, f"{last_rsi:.2f}", "RSI bullish but not overextended"),
            condition("rsi_sell_zone_ok", 28.0 <= last_rsi <= 50.0, f"{last_rsi:.2f}", "RSI bearish but not exhausted"),
            condition("vwap_real_volume_weighted", volume_available and last_volume > 0 and last_vwap > 0, f"volume={last_volume:.4f}", vwap_reason),
        ]
        buy_score = sum(30.0 for item in (conds[0], conds[2], conds[4]) if item.ok)
        sell_score = sum(30.0 for item in (conds[1], conds[3], conds[5]) if item.ok)
        score = max(buy_score, sell_score)
        side = "WAIT"
        if bullish and buy_score >= min_score:
            side = "BUY"
        elif bearish and sell_score >= min_score:
            side = "SELL"
        blocked = side == "WAIT"
        reasons = [] if not blocked else ["ema_vwap_confluence_not_met"]
        if not volume_available:
            reasons.append("vwap_volume_unavailable_fallback")
        sl, tp = (None, None)
        if side in {"BUY", "SELL"}:
            sl, tp = risk_levels(last_close, f(atr_value, last_close * 0.01), side)
        return make_signal(
            strategy=self.strategy_id,
            signal=side,
            score=score,
            conditions=conds,
            entry_price=last_close if side != "WAIT" else None,
            sl=sl,
            tp=tp,
            risk_pct=1.0 if side != "WAIT" else None,
            blocked=blocked or not volume_available,
            block_reasons=reasons,
        )
