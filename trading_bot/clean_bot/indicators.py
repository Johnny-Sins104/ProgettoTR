from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]
    out["ema20"] = close.ewm(span=20, adjust=False).mean()
    out["ema50"] = close.ewm(span=50, adjust=False).mean()
    out["ema200"] = close.ewm(span=200, adjust=False).mean()
    out["vol20"] = volume.rolling(20).mean()
    out["volume_ratio_20"] = volume / out["vol20"].replace(0, pd.NA)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["atr_pct"] = out["atr14"] / close.replace(0, pd.NA) * 100.0
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["rsi14"] = 100 - (100 / (1 + rs))
    out["range_low_96"] = low.rolling(96).min()
    out["range_high_96"] = high.rolling(96).max()
    width = (out["range_high_96"] - out["range_low_96"]).replace(0, pd.NA)
    out["range_pos_96"] = (close - out["range_low_96"]) / width
    out["range_low_400"] = low.rolling(400).min()
    out["range_high_400"] = high.rolling(400).max()
    width400 = (out["range_high_400"] - out["range_low_400"]).replace(0, pd.NA)
    out["range_pos_400"] = (close - out["range_low_400"]) / width400
    out["prior_high_48"] = high.shift(1).rolling(48).max()
    out["prior_low_48"] = low.shift(1).rolling(48).min()
    out["prior_high_288"] = high.shift(1).rolling(288).max()
    out["prior_low_288"] = low.shift(1).rolling(288).min()
    out["prior_high_576"] = high.shift(1).rolling(576).max()
    out["prior_low_576"] = low.shift(1).rolling(576).min()
    out["prior_high_1152"] = high.shift(1).rolling(1152).max()
    out["prior_low_1152"] = low.shift(1).rolling(1152).min()
    out["body"] = (close - out["Open"]).abs()
    candle_range = (high - low).replace(0, pd.NA)
    out["body_ratio"] = out["body"] / candle_range
    out["lower_wick_ratio"] = (pd.concat([close, out["Open"]], axis=1).min(axis=1) - low) / candle_range
    out["upper_wick_ratio"] = (high - pd.concat([close, out["Open"]], axis=1).max(axis=1)) / candle_range
    return out
