from __future__ import annotations

import pandas as pd

from trading_bot.strategy_runtime.strategy_signal_schema import condition, make_signal
from trading_bot.strategies.base_strategy import BaseStrategy, atr, column, f, risk_levels


class IchimokuStrategy(BaseStrategy):
    strategy_id = "ichimoku"
    display_name = "Ichimoku"

    def evaluate(self, df: pd.DataFrame, *, asset: str = "", timeframe: str = "") -> dict:
        if len(df) < 80:
            return self._wait("insufficient_history")
        high = column(df, "High")
        low = column(df, "Low")
        close = column(df, "Close")
        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2.0
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2.0
        span_a = (tenkan + kijun) / 2.0
        span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2.0
        last_close = f(close.iloc[-1])
        last_tenkan = f(tenkan.iloc[-1])
        last_kijun = f(kijun.iloc[-1])
        last_a = f(span_a.iloc[-1])
        last_b = f(span_b.iloc[-1])
        cloud_top = max(last_a, last_b)
        cloud_bottom = min(last_a, last_b)
        above_kumo = last_close > cloud_top
        below_kumo = last_close < cloud_bottom
        tenkan_above_kijun = last_tenkan > last_kijun
        tenkan_below_kijun = last_tenkan < last_kijun
        bullish_cloud = last_a > last_b
        bearish_cloud = last_a < last_b
        conds = [
            condition("price_above_kumo", above_kumo, f"{last_close:.6f}>{cloud_top:.6f}", "bullish location"),
            condition("price_below_kumo", below_kumo, f"{last_close:.6f}<{cloud_bottom:.6f}", "bearish location"),
            condition("tenkan_kijun_direction", tenkan_above_kijun or tenkan_below_kijun, f"tenkan={last_tenkan:.6f},kijun={last_kijun:.6f}", "conversion/base direction"),
            condition("kumo_color_direction", bullish_cloud or bearish_cloud, f"span_a={last_a:.6f},span_b={last_b:.6f}", "cloud direction"),
        ]
        bullish_count = sum(1 for item in (above_kumo, tenkan_above_kijun, bullish_cloud) if item)
        bearish_count = sum(1 for item in (below_kumo, tenkan_below_kijun, bearish_cloud) if item)
        signal = "WAIT"
        if bullish_count >= 2:
            signal = "BUY"
        elif bearish_count >= 2:
            signal = "SELL"
        score = 0.0
        if signal != "WAIT":
            score = max(bullish_count, bearish_count) / 3.0 * 100.0
        elif above_kumo or below_kumo:
            score = 40.0
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
            block_reasons=["ichimoku_structure_not_aligned"] if blocked else [],
        )
