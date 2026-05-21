import os


class Config:
    # Exchange — Binance Futures USDT-M (commissioni 5x più basse di Spot)
    EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binanceusdm")
    SYMBOL:      str = os.getenv("SYMBOL",      "BTC/USDT")
    TIMEFRAME:   str = os.getenv("TIMEFRAME",   "15m")

    # Embargo gap configurabile (in candele) per neutralizzare la correlazione seriale
    EMBARGO_GAP: int = int(os.getenv("EMBARGO_GAP", "100"))

    # Commissioni: Binance Futures Maker = 0.02% per side (0.04% round-trip)
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.0002"))

    # Credenziali exchange
    API_KEY:    str = os.getenv("API_KEY",    "")
    API_SECRET: str = os.getenv("API_SECRET", "")

    # Telegram
    TELEGRAM_TOKEN:   str = os.getenv("TELEGRAM_TOKEN",   "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Evolved Parameters (Deep Sweep su 76,800 combinazioni — 10k candele 5m)
    ATR_MULT:       float = float(os.getenv("ATR_MULT",     "2.0"))
    TRENDING_RR:    float = float(os.getenv("TRENDING_RR",    "2.0"))
    RANGING_RR:     float = float(os.getenv("RANGING_RR",     "2.0"))
    TP1_RR:         float = float(os.getenv("TP1_RR",         "1.5"))
    ADX_THRESHOLD:  float = float(os.getenv("ADX_THRESHOLD",  "33.86"))
    
    TRENDING_THRESHOLD: int = int(os.getenv("TRENDING_THRESHOLD", "60"))
    RANGING_THRESHOLD:  int = int(os.getenv("RANGING_THRESHOLD",  "30"))

    WEIGHTS_TRENDING: dict[str, int] = {
        "ema": 14,
        "bias": 18,
        "engulfing": 25,
        "rsi": 25,
        "support": 16,
        "psy_level": 2
    }

    WEIGHTS_RANGING: dict[str, int] = {
        "ema": 21,
        "bias": 5,
        "engulfing": 22,
        "rsi": 39,
        "support": 4,
        "psy_level": 9
    }

    # Selected Risk Profile: DYNAMIC per ottimizzazione Kelly Criterion
    RISK_CLASS:     str   = os.getenv("RISK_CLASS",    "DYNAMIC")

    # Multi-Trade: numero massimo di trade aperti contemporaneamente
    MAX_CONCURRENT_TRADES: int = int(os.getenv("MAX_CONCURRENT_TRADES", "3"))

    # Strategy Mode: Attivazione sistema predittivo AI
    STRATEGY_MODE:               str   = os.getenv("STRATEGY_MODE", "AI_HYBRID")
    USE_SCALE_OUT:               bool  = False
    USE_CONFLUENCE:              bool  = False

    # Defensive Risk Enhancements: Break-Even ottimizzato a 1.5x
    USE_BREAKEVEN:               bool  = True
    USE_BREAKEVEN_ON_TP1:        bool  = False
    BREAKEVEN_TRIGGER_RATIO:     float = 1.5
    USE_COMMISSION_AWARE_SIZING: bool  = True

    # Profit Target — il bot si ferma quando il saldo raggiunge questo % di guadagno
    PROFIT_TARGET_PCT: float = float(os.getenv("PROFIT_TARGET_PCT", "0.60"))

    # AI Configuration: Meta-Labeling & Confidence Filtering
    AI_ENABLED:         bool  = True
    AI_WEIGHT:          float = 0.40
    AI_MIN_CONFIDENCE:  float = 70.0      # Probabilità minima predetta aumentata al 70%
    AI_MIN_SAMPLES:     int   = 80        # Ridotto per allinearsi con la frequenza dei setup tecnici (meta-labeling)
    AI_RETRAIN_EVERY:   int   = 500
    AI_MODEL_PATH:      str   = os.path.join("data", "ai_model.pkl")
    AI_FEATURES_PATH:   str   = os.path.join("data", "market_features.parquet")
    AI_USE_EXPANDED_DATASET: bool = os.getenv("AI_USE_EXPANDED_DATASET", "1") == "1"
    AI_EXPANDED_DATASET_PATH: str = os.getenv("AI_EXPANDED_DATASET_PATH", os.path.join("data", "datasets", "meta_label_dataset.parquet"))
    AI_EXPANDED_MIN_SAMPLES: int = int(os.getenv("AI_EXPANDED_MIN_SAMPLES", "10000"))
    AI_MIN_REGIME_SAMPLES: int = int(os.getenv("AI_MIN_REGIME_SAMPLES", "1000"))

    # Parquet Dataset Metadata & Integrity Rules
    DATASET_VERSION:            str   = "1.0.0"
    MAX_NULL_TOLERANCE:         float = 0.05
    EXPECTED_TIMEFRAME_MINUTES: int   = 15

    # Meta-Labeling Thresholds
    META_PROB_THRESHOLD: float = 55.0     # Probabilità calibrata minima in % per accettare il trade
    META_QUALITY_THRESHOLD: float = 50.0  # Punteggio minimo di qualità tecnica per accettare il trade

    # Kelly Criterion Configuration
    USE_KELLY_SIZING:   bool  = True
    KELLY_FRACTION:     float = 0.5         # Half-Kelly baseline (full-Kelly is typically too aggressive)
    KELLY_FRACTION_TRENDING: float = 0.50   # Kelly fraction in trending regimes (higher edge clarity)
    KELLY_FRACTION_RANGING:  float = 0.35   # Kelly fraction in ranging regimes (lower edge reliability)

    # ── Dynamic Risk Engine — Volatility Regime ───────────────────────────────
    VOL_LOOKBACK:       int   = 50          # ATR samples for rolling median (vol regime classification)
    # Thresholds expressed as ATR / rolling_median ratios:
    #   ratio < 0.75  → LOW_VOL   (risk×1.1,  max_lev=10x)
    #   ratio <= 1.40 → NORMAL    (risk×1.0,  max_lev=8x)
    #   ratio <= 2.00 → HIGH_VOL  (risk×0.6,  max_lev=5x)
    #   ratio > 2.00  → EXTREME   (risk×0.3,  max_lev=3x)

    # ── Dynamic Risk Engine — Drawdown Circuit-Breaker ────────────────────────
    DD_CAUTION_PCT:     float = 8.0         # DD% entry → CAUTION   (risk×0.60)
    DD_REDUCED_PCT:     float = 15.0        # DD% entry → REDUCED    (risk×0.35)
    DD_PROTECTED_PCT:   float = 22.0        # DD% entry → PROTECTED  (risk×0.15)

    # ── Dynamic Risk Engine — Equity Curve Protection ─────────────────────────
    DAILY_LOSS_LIMIT_PCT: float = 5.0       # Block new entries if daily PnL < -5%
    PROFIT_LOCK_PCT:      float = 30.0      # Lock minimum risk floor once +30% above initial
    MAX_LEVERAGE:         float = 10.0      # Absolute hard cap on leverage (overrides vol regime)

    # Dynamic profile safety caps.
    # These caps apply only to the DYNAMIC profile in backtests/live sizing.
    # They prevent high Kelly outputs from risking institutionally unacceptable
    # fractions of equity on a single trade, especially on small accounts.
    DYNAMIC_DEFAULT_RISK_PCT: float = float(os.getenv("DYNAMIC_DEFAULT_RISK_PCT", "0.02"))
    DYNAMIC_MAX_RISK_PCT:     float = float(os.getenv("DYNAMIC_MAX_RISK_PCT",     "0.03"))
    DYNAMIC_MAX_LEVERAGE:     float = float(os.getenv("DYNAMIC_MAX_LEVERAGE",     "4.0"))

    # ── Execution Simulation Model ───────────────────────────────────────────
    # Enable realistic execution friction in backtests (slippage, spread, fills)
    EXECUTION_MODEL_ENABLED:  bool  = True

    # Slippage model calibration factors (1.0 = default empirical estimates)
    # Increase above 1.0 to stress-test under worse-than-average conditions
    SLIPPAGE_ATR_FACTOR:      float = float(os.getenv("SLIPPAGE_ATR_FACTOR",  "1.0"))
    SLIPPAGE_SPREAD_FACTOR:   float = float(os.getenv("SLIPPAGE_SPREAD_FACTOR", "1.0"))
    SLIPPAGE_IMPACT_FACTOR:   float = float(os.getenv("SLIPPAGE_IMPACT_FACTOR", "1.0"))

    # Liquidity model calibration factors
    FILL_PROB_FACTOR:         float = float(os.getenv("FILL_PROB_FACTOR",    "1.0"))
    PARTIAL_FILL_FACTOR:      float = float(os.getenv("PARTIAL_FILL_FACTOR", "1.0"))
    DEPTH_FACTOR:             float = float(os.getenv("DEPTH_FACTOR",        "1.0"))

    # Execution model stochastic mode: True adds trade-to-trade variation
    # (realistic), False uses deterministic median estimates (reproducible)
    EXECUTION_RANDOMIZE:      bool  = True

    # Legacy variables
    BUY_THRESHOLD:  int   = int(os.getenv("BUY_THRESHOLD",  "70"))
    SELL_THRESHOLD: int   = int(os.getenv("SELL_THRESHOLD", "-70"))
    RISK_REWARD:    float = float(os.getenv("RISK_REWARD",  "2.0"))
    TARGET_RR:      float = float(os.getenv("TARGET_RR",    "2.0"))
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", "0.02"))