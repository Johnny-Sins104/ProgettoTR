import pandas as pd
from config import Config

# Pesi per il Market Regime Switching
WEIGHTS_TRENDING: dict[str, int] = Config.WEIGHTS_TRENDING
WEIGHTS_RANGING: dict[str, int] = Config.WEIGHTS_RANGING


class DecisionEngine:

    def __init__(
        self,
        weights_trending: dict[str, int] | None = None,
        weights_ranging: dict[str, int] | None = None,
        trending_threshold: int | None = None,
        ranging_threshold: int | None = None,
    ) -> None:
        self.weights_trending: dict[str, int] = (weights_trending or Config.WEIGHTS_TRENDING).copy()
        self.weights_ranging: dict[str, int] = (weights_ranging or Config.WEIGHTS_RANGING).copy()
        self.trending_threshold: int = trending_threshold if trending_threshold is not None else Config.TRENDING_THRESHOLD
        self.ranging_threshold: int = ranging_threshold if ranging_threshold is not None else Config.RANGING_THRESHOLD

    def check_confluence(self, row, verdict: str) -> tuple[str, str]:
        """
        Verifica la confluenza istituzionale dei segnali.
        """
        has_pattern = False
        cdl_eng = row.get("cdl_engulfing", 0)
        cdl_doji = row.get("cdl_doji", 0)
        
        if verdict == "BUY":
            has_pattern = bool(cdl_eng == 100 or cdl_doji == 100)
        elif verdict == "SELL":
            has_pattern = bool(cdl_eng == -100 or cdl_doji == 100)

        has_sr = False
        if verdict == "BUY":
            has_sr = bool(row.get("near_support", False))
        elif verdict == "SELL":
            has_sr = bool(row.get("near_resistance", False))

        has_psy = bool(float(row.get("dist_to_psy_level", 999)) < 0.2)

        has_bias = False
        bias_val = row.get("volume_bias", "NEUTRAL")
        if verdict == "BUY" and bias_val == "BULLISH":
            has_bias = True
        elif verdict == "SELL" and bias_val == "BEARISH":
            has_bias = True

        if has_pattern and has_sr and has_psy and has_bias:
            return "GREEN", "Pattern+Support+Psy+Bias"

        if has_pattern and has_sr:
            return "YELLOW", "Pattern+Support"

        return "RED", "None"

    def evaluate(
        self, df: pd.DataFrame
    ) -> tuple[str, int, dict[str, bool], str | None, str, str]:
        """
        Punto di ingresso principale per la valutazione del segnale.
        Applica i filtri tecnici, AI e MTF in cascata.
        """
        if Config.STRATEGY_MODE == "AI_HYBRID":
            verdict, score, conf, entry_type, conf_verdict, conf_comb = self._evaluate_ai_hybrid(df)
        elif Config.STRATEGY_MODE == "EMA_TREND":
            verdict, score, conf, entry_type, conf_verdict, conf_comb = self._evaluate_ema_trend(df)
        else:
            verdict, score, conf, entry_type, conf_verdict, conf_comb = self._evaluate_score(df)

        # ── REGOLA RIGIDA MULTI-TIMEFRAME: EMA 1h 200 ── #
        row = df.iloc[-1]
        close_price = float(row["Close"])
        ema_1h_200 = float(row.get("ema_1h_200", 0))

        if ema_1h_200 > 0:
            if verdict == "BUY" and close_price <= ema_1h_200:
                verdict = "HOLD"
                entry_type = None
                conf_verdict = "RED"
                conf_comb = "MTF_Filtered(Price<=EMA_1h)"
            elif verdict == "SELL" and close_price >= ema_1h_200:
                verdict = "HOLD"
                entry_type = None
                conf_verdict = "RED"
                conf_comb = "MTF_Filtered(Price>=EMA_1h)"

        return (verdict, score, conf, entry_type, conf_verdict, conf_comb)

    def _evaluate_ai_hybrid(
        self, df: pd.DataFrame
    ) -> tuple[str, int, dict[str, bool], str | None, str, str]:
        """
        AI HYBRID STRATEGY: Due stadi Lopez de Prado Meta-Labeling.
        Stage 1 (Primary Model): Rules-based Technical scoring.
        Stage 2 (Secondary/Meta Model): XGBoost accepts/rejects setup based on p_cal and setup_quality.
        """
        # Stage 1: Calcolo score tecnico base (Primary Model)
        tech_verdict, tech_score, conf, entry_type, conf_verdict, conf_comb = self._evaluate_score(df)
        
        from core.data_collector import DataCollector
        from core.ai_engine import TradingAI
        from core.setup_filter import SetupFilter
        
        ai = TradingAI()
        
        # Estrazione features depurate (Clean-Data)
        features = DataCollector.extract_features(df, len(df) - 1)
        
        if tech_verdict not in ("BUY", "SELL"):
            conf["ai_prob"] = 50.0
            conf["setup_quality"] = 0.0
            conf["tech_score"] = tech_score
            return (tech_verdict, tech_score, conf, entry_type, conf_verdict, conf_comb)
            
        # Calcolo setup_quality per candidati BUY o SELL tramite SetupFilter
        volume_ratio = features.get("volume_ratio", 1.0)
        is_tech_ok, setup_quality = SetupFilter.evaluate_setup(tech_verdict, df.iloc[-1], volume_ratio)
        features["setup_quality"] = setup_quality
        
        if not ai.is_ready():
            conf["ai_prob"] = 50.0
            conf["setup_quality"] = setup_quality
            conf["tech_score"] = tech_score
            return (tech_verdict, tech_score, conf, entry_type, conf_verdict, conf_comb)
            
        # Rileva regime di mercato attivo ed esegue il logging dell'instradamento
        regime = ai.detect_regime(features)
        print(f"DEBUG: [AI_HYBRID] Active market regime: {regime} | Routing to {regime} model")
        
        # Predizione probabilità con Symmetry Transformation interna all'Engine
        p_cal = ai.predict_probability(features, side=tech_verdict)
        
        # Mappa probabilità (0-100) su score (-100 a +100) per hybrid_score diagnostico
        ai_score = (p_cal - 50.0) * 2.0
        hybrid_score = int(tech_score * (1.0 - Config.AI_WEIGHT) + ai_score * Config.AI_WEIGHT)
        
        # Log Debug per monitoraggio real-time con info sul regime
        print(f"DEBUG: [AI_HYBRID] Tech Score: {tech_score} | Calibrated Prob: {p_cal:.1f}% | Quality Score: {setup_quality:.1f} | Regime: {regime}")
        
        conf["ai_prob"] = p_cal
        conf["setup_quality"] = setup_quality
        conf["tech_score"] = tech_score
        
        # ── STAGE 2: GATING META-LABELING (ACCEPT/REJECT) ──
        if p_cal >= Config.META_PROB_THRESHOLD and is_tech_ok:
            # Trade Accettato!
            verdict = tech_verdict
            conf_comb = f"{conf_comb}+Meta_OK(p:{p_cal:.1f}%,q:{setup_quality:.1f})"
        else:
            # Trade Rifiutato!
            verdict = "HOLD"
            entry_type = None
            conf_verdict = "RED"
            conf_comb = f"Meta_Filtered(p:{p_cal:.1f}%,q:{setup_quality:.1f})"
            
        return (verdict, hybrid_score, conf, entry_type, conf_verdict, conf_comb)

    def _evaluate_ema_trend(
        self, df: pd.DataFrame
    ) -> tuple[str, int, dict[str, bool], str | None, str, str]:
        """
        EMA TREND FOLLOWING - Strategia robusta orientata al trend.
        """
        row = df.iloc[-1]
        close = float(row["Close"])
        ema200 = float(row.get("ema_200", 0))
        rsi = float(row.get("rsi_14", 50))
        eng = row.get("cdl_engulfing", 0)
        bias = row.get("volume_bias", "NEUTRAL")

        conf = {"ema": False, "engulfing": False, "rsi": False, "bias": False}
        score = 0
        verdict = "HOLD"
        entry_type = None

        if ema200 <= 0:
            return ("HOLD", 0, conf, None, "RED", "None")

        trend_bull = close > ema200
        trend_bear = close < ema200

        if trend_bull:
            conf["ema"] = True
            score += 25
        elif trend_bear:
            conf["ema"] = True
            score -= 25

        if eng == 100:
            score += 25
            conf["engulfing"] = True
        elif eng == -100:
            score -= 25
            conf["engulfing"] = True

        if rsi < 65 if trend_bull else rsi > 35:
            conf["rsi"] = True

        if (trend_bull and bias == "BULLISH") or (trend_bear and bias == "BEARISH"):
            score += 25 if trend_bull else -25
            conf["bias"] = True

        if trend_bull and eng == 100 and conf["rsi"] and bias == "BULLISH":
            verdict, entry_type, score = "BUY", "MARKET", 100
        elif trend_bear and eng == -100 and conf["rsi"] and bias == "BEARISH":
            verdict, entry_type, score = "SELL", "MARKET", -100

        conf_verdict = "GREEN" if verdict != "HOLD" else "RED"
        conf_comb = "EMA+Engulfing+RSI+Bias" if verdict != "HOLD" else "None"

        return (verdict, score, conf, entry_type, conf_verdict, conf_comb)

    def _evaluate_score(
        self, df: pd.DataFrame
    ) -> tuple[str, int, dict[str, bool], str | None, str, str]:
        """
        Tecnica di scoring pesata basata sul Market Regime.
        """
        row = df.iloc[-1]
        regime = row.get("market_regime", "RANGING")
        w = self.weights_trending if regime == "TRENDING" else self.weights_ranging
        threshold = self.trending_threshold if regime == "TRENDING" else self.ranging_threshold

        score = 0
        conf = {k: False for k in w}

        if row["Close"] > row["ema_200"]:
            score += w.get("ema", 0); conf["ema"] = True
        elif row["Close"] < row["ema_200"]:
            score -= w.get("ema", 0); conf["ema"] = True

        bias_val = row.get("volume_bias", "NEUTRAL")
        if bias_val == "BULLISH":
            score += w.get("bias", 0); conf["bias"] = True
        elif bias_val == "BEARISH":
            score -= w.get("bias", 0); conf["bias"] = True

        if row["cdl_engulfing"] == 100:
            score += w.get("engulfing", 0); conf["engulfing"] = True
        elif row["cdl_engulfing"] == -100:
            score -= w.get("engulfing", 0); conf["engulfing"] = True

        rsi_val = row["rsi_14"]
        if rsi_val < 30:
            score += w.get("rsi", 0); conf["rsi"] = True
        elif rsi_val > 70:
            score -= w.get("rsi", 0); conf["rsi"] = True

        near_sup, near_res = row.get("near_support", False), row.get("near_resistance", False)
        if score > 0 and near_sup:
            score += w.get("support", 0); conf["support"] = True
        elif score < 0 and near_res:
            score -= w.get("support", 0); conf["support"] = True

        if float(row.get("dist_to_psy_level", 999)) < 0.2:
            conf["psy_level"] = True
            score += (w.get("psy_level", 0) if score > 0 else -w.get("psy_level", 0))

        # Decisione e filtraggio macro
        verdict = "HOLD"; entry_type = None
        ema_200, ema_400 = float(row.get("ema_200", 0)), float(row.get("ema_400", 0))
        range_pos_400 = float(row.get("range_pos_400", 0.5))

        if score >= threshold:
            verdict = "BUY"
            if regime == "TRENDING" and ema_200 <= ema_400: verdict = "HOLD"
            elif regime == "RANGING" and range_pos_400 > 0.6: verdict = "HOLD"
            
            if verdict == "BUY":
                if row["cdl_engulfing"] == 100 and bias_val == "BULLISH": entry_type = "MARKET"
                elif near_res: entry_type = "STOP"
                else: entry_type = "LIMIT"
                
        elif score <= -threshold:
            verdict = "SELL"
            if regime == "TRENDING" and ema_200 >= ema_400: verdict = "HOLD"
            elif regime == "RANGING" and range_pos_400 < 0.4: verdict = "HOLD"
            
            if verdict == "SELL":
                if row["cdl_engulfing"] == -100 and bias_val == "BEARISH": entry_type = "MARKET"
                elif near_sup: entry_type = "STOP"
                else: entry_type = "LIMIT"

        # Check Confluenza
        if verdict in ("BUY", "SELL"):
            if Config.USE_CONFLUENCE:
                conf_v, conf_c = self.check_confluence(row, verdict)
                if conf_v != "GREEN":
                    verdict, entry_type = "HOLD", None
                return verdict, score, conf, entry_type, conf_v, conf_c
            return verdict, score, conf, entry_type, "SCORE_ONLY", "ScoreOnly"

        return "HOLD", score, conf, None, "RED", "None"