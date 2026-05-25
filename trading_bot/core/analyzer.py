import pandas as pd
import pandas_ta as ta
import numpy as np
import numba


@numba.jit(nopython=True, cache=True)
def _compute_fvgs_numba(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(highs)
    in_bull_fvg = np.zeros(n, dtype=np.int32)
    in_bear_fvg = np.zeros(n, dtype=np.int32)
    
    max_gaps = 2000
    
    bull_tops = np.zeros(max_gaps, dtype=np.float64)
    bull_bottoms = np.zeros(max_gaps, dtype=np.float64)
    bull_active = np.zeros(max_gaps, dtype=np.bool_)
    
    bear_tops = np.zeros(max_gaps, dtype=np.float64)
    bear_bottoms = np.zeros(max_gaps, dtype=np.float64)
    bear_active = np.zeros(max_gaps, dtype=np.bool_)
    
    for idx in range(2, n):
        if highs[idx-2] < lows[idx]:
            for j in range(max_gaps):
                if not bull_active[j]:
                    bull_tops[j] = lows[idx]
                    bull_bottoms[j] = highs[idx-2]
                    bull_active[j] = True
                    break
        
        if lows[idx-2] > highs[idx]:
            for j in range(max_gaps):
                if not bear_active[j]:
                    bear_tops[j] = lows[idx-2]
                    bear_bottoms[j] = highs[idx]
                    bear_active[j] = True
                    break
                    
        curr_close = closes[idx]
        curr_low = lows[idx]
        curr_high = highs[idx]
        
        is_inside_bull = 0
        for j in range(max_gaps):
            if bull_active[j]:
                if curr_low <= bull_bottoms[j]:
                    bull_active[j] = False
                else:
                    if bull_bottoms[j] <= curr_close <= bull_tops[j]:
                        is_inside_bull = 1
        in_bull_fvg[idx] = is_inside_bull
        
        is_inside_bear = 0
        for j in range(max_gaps):
            if bear_active[j]:
                if curr_high >= bear_tops[j]:
                    bear_active[j] = False
                else:
                    if bear_bottoms[j] <= curr_close <= bear_tops[j]:
                        is_inside_bear = 1
        in_bear_fvg[idx] = is_inside_bear
        
    return in_bull_fvg, in_bear_fvg


class TechnicalAnalyzer:

    def add_indicators(self, df: pd.DataFrame, is_live: bool = False) -> pd.DataFrame:
        # pandas_ta richiede colonne lowercase
        df_ta = df.copy()
        if is_live and len(df_ta) > 1000:
            df_ta = df_ta.iloc[-1000:]
        df_ta.columns = df_ta.columns.str.lower()

        # EMA 200
        df_ta["ema_200"] = ta.ema(df_ta["close"], length=200)

        # EMA 400
        df_ta["ema_400"] = ta.ema(df_ta["close"], length=400)

        # EMA 200 su timeframe 1h resamplato a 5m (senza lookahead bias)
        try:
            if isinstance(df_ta.index, pd.DatetimeIndex):
                df_1h = df_ta["close"].resample("1h").last()
                ema_1h_raw = ta.ema(df_1h, length=200)
                # Shift di 1 periodo a livello orario (l'EMA dell'ora X è disponibile solo all'inizio dell'ora X+1)
                ema_1h_shifted = ema_1h_raw.shift(1)
                df_ta["ema_1h_200"] = ema_1h_shifted.reindex(df_ta.index, method="ffill")
            else:
                df_ta["ema_1h_200"] = 0.0
        except Exception as e:
            df_ta["ema_1h_200"] = 0.0

        # RSI 14
        df_ta["rsi_14"] = ta.rsi(df_ta["close"], length=14)

        # Pattern Engulfing (manuale, senza TA-Lib)
        prev = df_ta.shift(1)
        bull = (
            (prev["close"] < prev["open"]) &   # candela prev rossa
            (df_ta["close"] > df_ta["open"]) &  # candela attuale verde
            (df_ta["open"]  <= prev["close"]) &
            (df_ta["close"] >  prev["open"])
        )
        bear = (
            (prev["close"] > prev["open"]) &    # candela prev verde
            (df_ta["close"] < df_ta["open"]) &  # candela attuale rossa
            (df_ta["open"]  >= prev["close"]) &
            (df_ta["close"] <  prev["open"])
        )
        df_ta["cdl_engulfing"] = 0
        df_ta.loc[bull, "cdl_engulfing"] =  100
        df_ta.loc[bear, "cdl_engulfing"] = -100

        # Pattern Doji (manuale): corpo <= 10% del range della candela
        body  = (df_ta["close"] - df_ta["open"]).abs()
        range_ = df_ta["high"] - df_ta["low"]
        df_ta["cdl_doji"] = 0
        df_ta.loc[(range_ > 0) & (body / range_ <= 0.1), "cdl_doji"] = 100

        # ATR 14
        df_ta["atr"] = ta.atr(df_ta["high"], df_ta["low"], df_ta["close"], length=14)

        # ── PRICE ACTION ────────────────────────────────────────────────── #

        # 1. Livelli Psicologici
        #    Multipli di 250, 500, 1000 — si approssima al livello tondo più vicino
        #    e si calcola la distanza percentuale assoluta dal Close.
        def _nearest_psy(price: float, step: float = 250.0) -> float:
            return round(price / step) * step

        df_ta["_psy_level"] = df_ta["close"].apply(lambda p: _nearest_psy(p))
        df_ta["dist_to_psy_level"] = (
            (df_ta["close"] - df_ta["_psy_level"]).abs() / df_ta["close"]
        ) * 100  # in %
        df_ta.drop(columns=["_psy_level"], inplace=True)

        # 2. Swing Highs / Swing Lows su finestra mobile 20 candele
        WIN = 20
        df_ta["local_support"]    = df_ta["low"].shift(1).rolling(window=WIN).min()
        df_ta["local_resistance"] = df_ta["high"].shift(1).rolling(window=WIN).max()

        # 4. Macro Swing Highs / Swing Lows su finestra mobile 400 candele (shifted di 1 per evitare self-referencing)
        MACRO_WIN = 400
        df_ta["macro_support"]    = df_ta["low"].shift(1).rolling(window=MACRO_WIN).min()
        df_ta["macro_resistance"] = df_ta["high"].shift(1).rolling(window=MACRO_WIN).max()

        # 5. Posizione relativa all'interno del macro range [0.0, 1.0]
        denom = df_ta["macro_resistance"] - df_ta["macro_support"]
        df_ta["range_pos_400"] = (df_ta["close"] - df_ta["macro_support"]) / denom.replace(0, 1e-8)

        # 3. Prossimità al supporto/resistenza (entro 1%)
        df_ta["near_support"] = (
            (df_ta["close"] - df_ta["local_support"]).abs() / df_ta["close"]
        ) <= 0.01
        df_ta["near_resistance"] = (
            (df_ta["close"] - df_ta["local_resistance"]).abs() / df_ta["close"]
        ) <= 0.01

        # ── MARKET BIAS ─────────────────────────────────────────────────── #

        # Volume Bias sulle ultime 5 candele (60% threshold)
        BIAS_WIN = 5
        is_bull_candle = (df_ta["close"] > df_ta["open"]).astype(float)
        is_bear_candle = (df_ta["close"] < df_ta["open"]).astype(float)

        bull_vol = (df_ta["volume"] * is_bull_candle).rolling(window=BIAS_WIN).sum()
        bear_vol = (df_ta["volume"] * is_bear_candle).rolling(window=BIAS_WIN).sum()
        total_vol = (bull_vol + bear_vol).replace(0, 1e-8)

        df_ta["volume_delta"] = bull_vol - bear_vol
        
        df_ta["volume_bias"] = "NEUTRAL"
        df_ta.loc[bull_vol / total_vol >= 0.60, "volume_bias"] = "BULLISH"
        df_ta.loc[bear_vol / total_vol >= 0.60, "volume_bias"] = "BEARISH"

        # ── FAIR VALUE GAPS (FVG) ────────────────────────────────────────── #
        highs = df_ta["high"].values
        lows = df_ta["low"].values
        closes = df_ta["close"].values

        try:
            in_bull_fvg, in_bear_fvg = _compute_fvgs_numba(highs, lows, closes)
        except Exception:
            # Fallback a loop Python nativo se Numba fallisce
            bull_fvgs = []  # list of {"top": float, "bottom": float}
            bear_fvgs = []  # list of {"top": float, "bottom": float}
            in_bull_fvg = [0] * len(df_ta)
            in_bear_fvg = [0] * len(df_ta)

            for idx in range(2, len(df_ta)):
                if highs[idx-2] < lows[idx]:
                    bull_fvgs.append({"top": lows[idx], "bottom": highs[idx-2]})
                if lows[idx-2] > highs[idx]:
                    bear_fvgs.append({"top": lows[idx-2], "bottom": highs[idx]})

                curr_close = closes[idx]
                curr_low = lows[idx]
                curr_high = highs[idx]

                active_bull = []
                is_inside_bull = 0
                for fvg in bull_fvgs:
                    if curr_low <= fvg["bottom"]:
                        continue
                    active_bull.append(fvg)
                    if fvg["bottom"] <= curr_close <= fvg["top"]:
                        is_inside_bull = 1
                bull_fvgs = active_bull
                in_bull_fvg[idx] = is_inside_bull

                active_bear = []
                is_inside_bear = 0
                for fvg in bear_fvgs:
                    if curr_high >= fvg["top"]:
                        continue
                    active_bear.append(fvg)
                    if fvg["bottom"] <= curr_close <= fvg["top"]:
                        is_inside_bear = 1
                bear_fvgs = active_bear
                in_bear_fvg[idx] = is_inside_bear

        df_ta["in_bull_fvg"] = in_bull_fvg
        df_ta["in_bear_fvg"] = in_bear_fvg

        # ── MARKET REGIME (ADX 14) ──────────────────────────────────────── #
        adx_df = ta.adx(df_ta["high"], df_ta["low"], df_ta["close"], length=14)
        if adx_df is not None and not adx_df.empty:
            adx_col = [c for c in adx_df.columns if "ADX" in c][0]
            df_ta["adx"] = adx_df[adx_col].fillna(0)
        else:
            df_ta["adx"] = 0.0

        from config import Config
        df_ta["market_regime"] = "RANGING"
        df_ta.loc[df_ta["adx"] > Config.ADX_THRESHOLD, "market_regime"] = "TRENDING"

        # ────────────────────────────────────────────────────────────────── #

        # Ripristina colonne originali uppercase + nuove lowercase
        rename_map = {c: c.capitalize() for c in ["open", "high", "low", "close", "volume"]}
        df_ta.rename(columns=rename_map, inplace=True)

        return df_ta.fillna(0)
