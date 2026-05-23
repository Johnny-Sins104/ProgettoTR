import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Config:
    # Exchange — Binance Futures USDT-M (commissioni 5x più basse di Spot)
    EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binanceusdm")
    SYMBOL:      str = os.getenv("SYMBOL",      "BTC/USDT")
    TIMEFRAME:   str = os.getenv("TIMEFRAME",   "15m")
    SUPPORTED_BACKTEST_TIMEFRAMES: tuple[str, ...] = ("15m", "5m", "3m")
    SUPPORTED_BACKTEST_SYMBOLS: tuple[str, ...] = tuple(x.strip() for x in os.getenv("SUPPORTED_BACKTEST_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT").split(",") if x.strip())
    MULTI_ASSET_ROBUSTNESS_REPORT_PATH: str = os.getenv("MULTI_ASSET_ROBUSTNESS_REPORT_PATH", os.path.join("data", "multi_asset_robustness_report.json"))
    ACTIVE_TIMEFRAME_PROFILE: dict = {}

    # Embargo gap configurabile (in candele) per neutralizzare la correlazione seriale
    EMBARGO_GAP: int = int(os.getenv("EMBARGO_GAP", "100"))



    # Prompt 28.10 — execution realism / slippage stress controls.
    EXECUTION_COST_MODEL: str = os.getenv("EXECUTION_COST_MODEL", "base")
    EXECUTION_COST_STRESS_REPORT_PATH: str = os.getenv("EXECUTION_COST_STRESS_REPORT_PATH", os.path.join("data", "execution_cost_stress_report.json"))
    EXECUTION_MAKER_FEE_BPS_SIDE: float = float(os.getenv("EXECUTION_MAKER_FEE_BPS_SIDE", "2.0"))
    EXECUTION_TAKER_FEE_BPS_SIDE: float = float(os.getenv("EXECUTION_TAKER_FEE_BPS_SIDE", "4.0"))
    EXECUTION_COST_BASE_MULTIPLIER: float = float(os.getenv("EXECUTION_COST_BASE_MULTIPLIER", "1.0"))
    EXECUTION_COST_CONSERVATIVE_MULTIPLIER: float = float(os.getenv("EXECUTION_COST_CONSERVATIVE_MULTIPLIER", "1.75"))
    EXECUTION_COST_SEVERE_MULTIPLIER: float = float(os.getenv("EXECUTION_COST_SEVERE_MULTIPLIER", "2.75"))
    EXECUTION_COST_TIMEFRAME_MULTIPLIER_15M: float = float(os.getenv("EXECUTION_COST_TIMEFRAME_MULTIPLIER_15M", "1.0"))
    EXECUTION_COST_TIMEFRAME_MULTIPLIER_5M: float = float(os.getenv("EXECUTION_COST_TIMEFRAME_MULTIPLIER_5M", "1.20"))
    EXECUTION_COST_TIMEFRAME_MULTIPLIER_3M: float = float(os.getenv("EXECUTION_COST_TIMEFRAME_MULTIPLIER_3M", "1.55"))
    EXECUTION_MAX_ATR_SLIPPAGE_BPS: float = float(os.getenv("EXECUTION_MAX_ATR_SLIPPAGE_BPS", "35.0"))
    EXECUTION_LATENCY_BPS_CONSERVATIVE: float = float(os.getenv("EXECUTION_LATENCY_BPS_CONSERVATIVE", "1.0"))
    EXECUTION_PARTIAL_FILL_PENALTY_BPS_SEVERE: float = float(os.getenv("EXECUTION_PARTIAL_FILL_PENALTY_BPS_SEVERE", "2.0"))

    # Prompt 28.8 — multi-timeframe research controls.
    # 5m/3m runs keep the same real-time WF span as 15m by scaling train/test/embargo
    # unless explicit WF_* environment variables are supplied.
    TIMEFRAME_COST_STRESS_ENABLED: bool = os.getenv("TIMEFRAME_COST_STRESS_ENABLED", "1") == "1"
    TIMEFRAME_COST_STRESS_5M: float = float(os.getenv("TIMEFRAME_COST_STRESS_5M", "1.25"))
    TIMEFRAME_COST_STRESS_3M: float = float(os.getenv("TIMEFRAME_COST_STRESS_3M", "1.60"))
    TIMEFRAME_COMPARISON_REPORT_PATH: str = os.getenv("TIMEFRAME_COMPARISON_REPORT_PATH", os.path.join("data", "timeframe_comparison_report.json"))

    # Prompt 28 — true rolling walk-forward controls.
    # WF_AUTO_ADAPTIVE keeps purge+embargo intact but shrinks train/test windows
    # when local backtests have fewer candles than the research default.
    WF_TRAIN_SIZE: int = int(os.getenv("WF_TRAIN_SIZE", "2000"))
    WF_TEST_SIZE: int = int(os.getenv("WF_TEST_SIZE", "500"))
    WF_LABEL_HORIZON: int = int(os.getenv("WF_LABEL_HORIZON", "100"))
    WF_MIN_TRAIN_SIZE: int = int(os.getenv("WF_MIN_TRAIN_SIZE", "250"))
    WF_TRAIN_MODE: str = os.getenv("WF_TRAIN_MODE", "rolling")
    WF_AUTO_ADAPTIVE: bool = os.getenv("WF_AUTO_ADAPTIVE", "1") == "1"
    WF_MIN_TEST_SIZE: int = int(os.getenv("WF_MIN_TEST_SIZE", "100"))

    # Prompt 28.1 — walk-forward evaluation-only controls.
    # Adaptive 1k-candle folds are useful for temporal diagnostics, but they are
    # too small to safely retrain XGBoost.  By default, WF folds evaluate the
    # already-trained global/multi-asset model unless explicitly allowed and the
    # fold contains enough local meta-label samples.
    WF_EVALUATION_ONLY: bool = os.getenv("WF_EVALUATION_ONLY", "1") == "1"
    WF_ALLOW_LOCAL_RETRAIN: bool = os.getenv("WF_ALLOW_LOCAL_RETRAIN", "0") == "1"
    WF_MIN_LOCAL_TRAIN_SAMPLES: int = int(os.getenv("WF_MIN_LOCAL_TRAIN_SAMPLES", "1000"))

    # Commissioni: Binance Futures Maker = 0.02% per side (0.04% round-trip)
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.0002"))

    # Credenziali exchange
    API_KEY:    str = os.getenv("API_KEY",    "")
    API_SECRET: str = os.getenv("API_SECRET", "")

    # Telegram
    TELEGRAM_TOKEN:   str = os.getenv("TELEGRAM_TOKEN",   "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    # Prompt 29 — paper trading / operations layer.
    PAPER_TRADING_ENABLED: bool = os.getenv("PAPER_TRADING_ENABLED", "1") == "1"
    PAPER_MODE_ONLY: bool = os.getenv("PAPER_MODE_ONLY", "1") == "1"
    PAPER_DEFAULT_TIMEFRAME: str = os.getenv("PAPER_DEFAULT_TIMEFRAME", "5m")
    PAPER_DEFAULT_COST_MODEL: str = os.getenv("PAPER_DEFAULT_COST_MODEL", "conservative")
    PAPER_INITIAL_BALANCE: float = float(os.getenv("PAPER_INITIAL_BALANCE", "1000"))
    PAPER_MAX_POSITIONS: int = int(os.getenv("PAPER_MAX_POSITIONS", "3"))
    PAPER_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_RISK_PER_TRADE_PCT", "0.005"))
    PAPER_STATE_PATH: str = os.getenv("PAPER_STATE_PATH", os.path.join("data", "paper_state.json"))
    PAPER_EVENTS_PATH: str = os.getenv("PAPER_EVENTS_PATH", os.path.join("data", "paper_events.jsonl"))
    PAPER_STATUS_PATH: str = os.getenv("PAPER_STATUS_PATH", os.path.join("data", "paper_status.json"))
    TELEGRAM_ALLOWED_USER_IDS: str = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")

    # Prompt 29.4.1/29.4.1a — clean console and proactive Telegram monitoring.
    PAPER_CONSOLE_VERBOSE: bool = os.getenv("PAPER_CONSOLE_VERBOSE", "0") == "1"
    PAPER_AI_DEBUG: bool = os.getenv("PAPER_AI_DEBUG", "0") == "1"
    PAPER_CONSOLE_HEADER_EVERY_N_CYCLES: int = int(os.getenv("PAPER_CONSOLE_HEADER_EVERY_N_CYCLES", "12"))
    PAPER_CONSOLE_SHOW_FLAT_MONITOR: bool = os.getenv("PAPER_CONSOLE_SHOW_FLAT_MONITOR", "0") == "1"

    TELEGRAM_PROACTIVE_ENABLED: bool = os.getenv("TELEGRAM_PROACTIVE_ENABLED", "1") == "1"
    TELEGRAM_NOTIFY_ON_START: bool = os.getenv("TELEGRAM_NOTIFY_ON_START", "1") == "1"
    TELEGRAM_NOTIFY_ON_SHUTDOWN: bool = os.getenv("TELEGRAM_NOTIFY_ON_SHUTDOWN", "1") == "1"
    TELEGRAM_NOTIFY_ON_SIGNAL: bool = os.getenv("TELEGRAM_NOTIFY_ON_SIGNAL", "1") == "1"
    TELEGRAM_NOTIFY_ON_ORDER: bool = os.getenv("TELEGRAM_NOTIFY_ON_ORDER", "1") == "1"
    TELEGRAM_NOTIFY_ON_POSITION_OPEN: bool = os.getenv("TELEGRAM_NOTIFY_ON_POSITION_OPEN", "1") == "1"
    TELEGRAM_NOTIFY_ON_POSITION_CLOSE: bool = os.getenv("TELEGRAM_NOTIFY_ON_POSITION_CLOSE", "1") == "1"
    TELEGRAM_NOTIFY_ON_TP_SL: bool = os.getenv("TELEGRAM_NOTIFY_ON_TP_SL", "1") == "1"
    TELEGRAM_NOTIFY_ON_DRIFT_WARN: bool = os.getenv("TELEGRAM_NOTIFY_ON_DRIFT_WARN", "1") == "1"
    TELEGRAM_NOTIFY_POSITION_EVERY_N_CYCLES: int = int(os.getenv("TELEGRAM_NOTIFY_POSITION_EVERY_N_CYCLES", "1"))
    TELEGRAM_NOTIFY_POSITION_EVERY_SECONDS: float = float(os.getenv("TELEGRAM_NOTIFY_POSITION_EVERY_SECONDS", "300"))
    TELEGRAM_NOTIFY_POSITION_PNL_DELTA_PCT: float = float(os.getenv("TELEGRAM_NOTIFY_POSITION_PNL_DELTA_PCT", "0.25"))
    TELEGRAM_NOTIFY_NO_SIGNAL_EVERY_N_CYCLES: int = int(os.getenv("TELEGRAM_NOTIFY_NO_SIGNAL_EVERY_N_CYCLES", "12"))
    TELEGRAM_NOTIFY_EVERY_CYCLE: bool = os.getenv("TELEGRAM_NOTIFY_EVERY_CYCLE", "0") == "1"
    TELEGRAM_PROACTIVE_DEDUP_SECONDS: float = float(os.getenv("TELEGRAM_PROACTIVE_DEDUP_SECONDS", "30"))
    TELEGRAM_PROACTIVE_MAX_MESSAGES_PER_MINUTE: int = int(os.getenv("TELEGRAM_PROACTIVE_MAX_MESSAGES_PER_MINUTE", "10"))


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

    # Prompt 26 — Macro + market-structure feature layer. External files are
    # optional; when absent, the dataset builder emits neutral defaults and
    # availability flags so the training path stays offline reproducible.
    MARKET_STRUCTURE_FEATURES_ENABLED: bool = os.getenv("MARKET_STRUCTURE_FEATURES_ENABLED", "1") == "1"
    MARKET_STRUCTURE_REPORT_PATH: str = os.getenv("MARKET_STRUCTURE_REPORT_PATH", os.path.join("data", "datasets", "market_structure_report.json"))
    FUNDING_DATA_PATH: str = os.getenv("FUNDING_DATA_PATH", "")
    OPEN_INTEREST_DATA_PATH: str = os.getenv("OPEN_INTEREST_DATA_PATH", "")
    BTC_DOMINANCE_DATA_PATH: str = os.getenv("BTC_DOMINANCE_DATA_PATH", "")

    # Parquet Dataset Metadata & Integrity Rules
    DATASET_VERSION:            str   = "1.0.0"
    MAX_NULL_TOLERANCE:         float = 0.05
    EXPECTED_TIMEFRAME_MINUTES: int   = int(os.getenv("EXPECTED_TIMEFRAME_MINUTES", "15"))

    # Meta-Labeling Thresholds
    META_PROB_THRESHOLD: float = 55.0     # Probabilità calibrata minima in % per accettare il trade
    META_QUALITY_THRESHOLD: float = 50.0  # Punteggio minimo di qualità tecnica per accettare il trade
    SIGNAL_DENSITY_DIAGNOSTICS: bool = os.getenv("SIGNAL_DENSITY_DIAGNOSTICS", "1") == "1"
    SIGNAL_DENSITY_REPORT_PATH: str = os.getenv("SIGNAL_DENSITY_REPORT_PATH", os.path.join("data", "signal_density_report.json"))
    # Prompt 29.4.2 — paper signal diagnostics. Diagnostic-only by default:
    # these settings never change trading decisions unless future prompts wire
    # a separate, explicitly validated paper-only unlock mode.
    PAPER_SIGNAL_DIAGNOSTICS_ENABLED: bool = os.getenv("PAPER_SIGNAL_DIAGNOSTICS_ENABLED", "1") == "1"
    PAPER_SIGNAL_DIAGNOSTICS_REPORT_PATH: str = os.getenv("PAPER_SIGNAL_DIAGNOSTICS_REPORT_PATH", os.path.join("data", "paper_signal_diagnostics_report.json"))
    PAPER_SIGNAL_DIAGNOSTICS_BACKFILL_ENABLED: bool = os.getenv("PAPER_SIGNAL_DIAGNOSTICS_BACKFILL_ENABLED", "1") == "1"
    PAPER_SIGNAL_DIAGNOSTICS_BACKFILL_REPORT_PATH: str = os.getenv("PAPER_SIGNAL_DIAGNOSTICS_BACKFILL_REPORT_PATH", os.path.join("data", "paper_signal_diagnostics_backfill_report.json"))
    PAPER_EXPLORATORY_SIGNAL_ANALYSIS: bool = os.getenv("PAPER_EXPLORATORY_SIGNAL_ANALYSIS", "1") == "1"
    PAPER_EXPLORATORY_META_PROB_THRESHOLD: float = float(os.getenv("PAPER_EXPLORATORY_META_PROB_THRESHOLD", "48.0"))
    PAPER_EXPLORATORY_RANGING_META_PROB_THRESHOLD: float = float(os.getenv("PAPER_EXPLORATORY_RANGING_META_PROB_THRESHOLD", "45.0"))
    PAPER_EXPLORATORY_MIN_SETUP_QUALITY: float = float(os.getenv("PAPER_EXPLORATORY_MIN_SETUP_QUALITY", "60.0"))
    PAPER_ENTRY_UNLOCK_ENABLED: bool = os.getenv("PAPER_ENTRY_UNLOCK_ENABLED", "0") == "1"

    # Prompt 29.4.3 — conservative threshold simulation / shadow unlock analysis.
    # Shadow-only by default: this never changes strategy gates, order flow, broker
    # state, paper positions, testnet, or live execution.
    PAPER_SHADOW_SIMULATION_ENABLED: bool = os.getenv("PAPER_SHADOW_SIMULATION_ENABLED", "1") == "1"
    PAPER_SHADOW_REPORT_PATH: str = os.getenv("PAPER_SHADOW_REPORT_PATH", os.path.join("data", "paper_shadow_unlock_report.json"))
    PAPER_SHADOW_INCLUDE_INFERRED: bool = os.getenv("PAPER_SHADOW_INCLUDE_INFERRED", "1") == "1"
    PAPER_SHADOW_MAX_HOLD_CYCLES: int = int(os.getenv("PAPER_SHADOW_MAX_HOLD_CYCLES", "12"))
    PAPER_SHADOW_STOP_LOSS_PCT: float = float(os.getenv("PAPER_SHADOW_STOP_LOSS_PCT", "0.0035"))
    PAPER_SHADOW_TP1_PCT: float = float(os.getenv("PAPER_SHADOW_TP1_PCT", "0.0035"))
    PAPER_SHADOW_TP2_PCT: float = float(os.getenv("PAPER_SHADOW_TP2_PCT", "0.0070"))

    # Prompt 29.4.4 — conservative paper-only shadow-to-paper unlock gate.
    # Default OFF. When enabled, this may convert only validated shadow-profile
    # candidates into paper orders. It is blocked for live/testnet by design.
    PAPER_UNLOCK_PROFILE: str = os.getenv("PAPER_UNLOCK_PROFILE", "BTC_ONLY_40_Q60")
    PAPER_UNLOCK_ALLOWED_SYMBOLS: str = os.getenv("PAPER_UNLOCK_ALLOWED_SYMBOLS", "BTC/USDT")
    PAPER_UNLOCK_ALLOWED_FILTERS: str = os.getenv("PAPER_UNLOCK_ALLOWED_FILTERS", "META_PROB_LOW")
    PAPER_UNLOCK_MIN_AI_PROB: float = float(os.getenv("PAPER_UNLOCK_MIN_AI_PROB", "40.0"))
    PAPER_UNLOCK_MIN_SETUP_QUALITY: float = float(os.getenv("PAPER_UNLOCK_MIN_SETUP_QUALITY", "60.0"))
    PAPER_UNLOCK_REQUIRE_TECH_GATE: bool = os.getenv("PAPER_UNLOCK_REQUIRE_TECH_GATE", "1") == "1"
    PAPER_UNLOCK_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_LIVE_BLOCK: bool = os.getenv("PAPER_UNLOCK_LIVE_BLOCK", "1") == "1"
    PAPER_UNLOCK_TAG: str = os.getenv("PAPER_UNLOCK_TAG", "PAPER_UNLOCK_29_4_4")

    # Prompt 29.4.4a — unlock rejection analysis. Diagnostic-only: reads
    # paper_events.jsonl and writes a report explaining why unlock candidates
    # were rejected. It never changes order flow, thresholds, testnet or live.
    PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED: bool = os.getenv("PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED", "1") == "1"
    PAPER_UNLOCK_REJECTION_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_REJECTION_REPORT_PATH", os.path.join("data", "paper_unlock_rejection_report.json"))

    # Prompt 29.5.0a — crypto intraday scenario engine. Diagnostic-only: builds
    # an explicit support/resistance/range/breakout/rejection scenario map from
    # real exchange OHLCV/indicator data. It never changes strategy decisions,
    # thresholds, order flow, testnet or live execution.
    PAPER_CRYPTO_SCENARIO_ENABLED: bool = os.getenv("PAPER_CRYPTO_SCENARIO_ENABLED", "1") == "1"
    PAPER_CRYPTO_SCENARIO_REPORT_PATH: str = os.getenv("PAPER_CRYPTO_SCENARIO_REPORT_PATH", os.path.join("data", "crypto_intraday_scenario_report.json"))
    CRYPTO_SCENARIO_SR_PROXIMITY_PCT: float = float(os.getenv("CRYPTO_SCENARIO_SR_PROXIMITY_PCT", "0.0035"))
    CRYPTO_SCENARIO_BREAKOUT_BUFFER_PCT: float = float(os.getenv("CRYPTO_SCENARIO_BREAKOUT_BUFFER_PCT", "0.0005"))
    CRYPTO_SCENARIO_MIN_BODY_RATIO: float = float(os.getenv("CRYPTO_SCENARIO_MIN_BODY_RATIO", "0.35"))
    CRYPTO_SCENARIO_REJECTION_WICK_RATIO: float = float(os.getenv("CRYPTO_SCENARIO_REJECTION_WICK_RATIO", "0.45"))
    CRYPTO_SCENARIO_VOLUME_RATIO_THRESHOLD: float = float(os.getenv("CRYPTO_SCENARIO_VOLUME_RATIO_THRESHOLD", "1.10"))
    CRYPTO_SCENARIO_NO_TRADE_LOW: float = float(os.getenv("CRYPTO_SCENARIO_NO_TRADE_LOW", "0.40"))
    CRYPTO_SCENARIO_NO_TRADE_HIGH: float = float(os.getenv("CRYPTO_SCENARIO_NO_TRADE_HIGH", "0.60"))
    CRYPTO_SCENARIO_RANGE_EXTREME_LOW: float = float(os.getenv("CRYPTO_SCENARIO_RANGE_EXTREME_LOW", "0.25"))
    CRYPTO_SCENARIO_RANGE_EXTREME_HIGH: float = float(os.getenv("CRYPTO_SCENARIO_RANGE_EXTREME_HIGH", "0.75"))

    # Prompt 29.5.0b — candlestick pattern feature engine + scenario integration.
    # Diagnostic-only: detects explicit candle patterns and integrates them with
    # the crypto scenario context. It never changes strategy decisions,
    # thresholds, order flow, testnet or live execution.
    PAPER_CANDLESTICK_PATTERNS_ENABLED: bool = os.getenv("PAPER_CANDLESTICK_PATTERNS_ENABLED", "1") == "1"
    PAPER_CANDLESTICK_PATTERN_REPORT_PATH: str = os.getenv("PAPER_CANDLESTICK_PATTERN_REPORT_PATH", os.path.join("data", "candlestick_pattern_report.json"))
    CANDLE_PATTERN_MIN_BODY_RATIO: float = float(os.getenv("CANDLE_PATTERN_MIN_BODY_RATIO", "0.25"))
    CANDLE_PATTERN_STRONG_BODY_RATIO: float = float(os.getenv("CANDLE_PATTERN_STRONG_BODY_RATIO", "0.55"))
    CANDLE_PATTERN_DOJI_BODY_RATIO: float = float(os.getenv("CANDLE_PATTERN_DOJI_BODY_RATIO", "0.12"))
    CANDLE_PATTERN_WICK_RATIO: float = float(os.getenv("CANDLE_PATTERN_WICK_RATIO", "0.45"))
    CANDLE_PATTERN_PIN_WICK_TO_BODY: float = float(os.getenv("CANDLE_PATTERN_PIN_WICK_TO_BODY", "2.0"))
    CANDLE_PATTERN_INSIDE_TOLERANCE_PCT: float = float(os.getenv("CANDLE_PATTERN_INSIDE_TOLERANCE_PCT", "0.0002"))
    CANDLE_PATTERN_OUTSIDE_TOLERANCE_PCT: float = float(os.getenv("CANDLE_PATTERN_OUTSIDE_TOLERANCE_PCT", "0.0002"))
    CANDLE_PATTERN_RECLAIM_BUFFER_PCT: float = float(os.getenv("CANDLE_PATTERN_RECLAIM_BUFFER_PCT", "0.0003"))
    CANDLE_PATTERN_RETEST_TOLERANCE_PCT: float = float(os.getenv("CANDLE_PATTERN_RETEST_TOLERANCE_PCT", "0.0015"))
    CANDLE_PATTERN_VOLUME_RATIO_THRESHOLD: float = float(os.getenv("CANDLE_PATTERN_VOLUME_RATIO_THRESHOLD", "1.10"))

    # Prompt 29.5.0c — pattern-conditioned shadow/backtest review.
    # Diagnostic-only: tests scenario + candlestick pattern candidates against
    # runtime events and optional historical OHLCV caches. It never changes
    # strategy decisions, thresholds, order flow, testnet or live execution.
    PATTERN_CONDITIONED_SHADOW_ENABLED: bool = os.getenv("PATTERN_CONDITIONED_SHADOW_ENABLED", "1") == "1"
    PATTERN_CONDITIONED_HISTORICAL_ENABLED: bool = os.getenv("PATTERN_CONDITIONED_HISTORICAL_ENABLED", "1") == "1"
    PATTERN_CONDITIONED_REPORT_PATH: str = os.getenv("PATTERN_CONDITIONED_REPORT_PATH", os.path.join("data", "pattern_conditioned_shadow_report.json"))
    PATTERN_CONDITIONED_SYMBOLS: str = os.getenv("PATTERN_CONDITIONED_SYMBOLS", os.getenv("PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT"))
    PATTERN_CONDITIONED_MAX_ROWS_PER_ASSET: int = int(os.getenv("PATTERN_CONDITIONED_MAX_ROWS_PER_ASSET", "5000"))
    PATTERN_CONDITIONED_MIN_WARMUP_ROWS: int = int(os.getenv("PATTERN_CONDITIONED_MIN_WARMUP_ROWS", "450"))
    PATTERN_CONDITIONED_EVAL_STRIDE: int = int(os.getenv("PATTERN_CONDITIONED_EVAL_STRIDE", "1"))
    PATTERN_CONDITIONED_HORIZONS: str = os.getenv("PATTERN_CONDITIONED_HORIZONS", "3,6,12")
    PATTERN_CONDITIONED_STOP_LOSS_PCT: float = float(os.getenv("PATTERN_CONDITIONED_STOP_LOSS_PCT", os.getenv("PAPER_SHADOW_STOP_LOSS_PCT", "0.0035")))
    PATTERN_CONDITIONED_TP1_PCT: float = float(os.getenv("PATTERN_CONDITIONED_TP1_PCT", os.getenv("PAPER_SHADOW_TP1_PCT", "0.0035")))
    PATTERN_CONDITIONED_TP2_PCT: float = float(os.getenv("PATTERN_CONDITIONED_TP2_PCT", os.getenv("PAPER_SHADOW_TP2_PCT", "0.0070")))
    PATTERN_CONDITIONED_MIN_OPERATIONAL_CANDIDATES: int = int(os.getenv("PATTERN_CONDITIONED_MIN_OPERATIONAL_CANDIDATES", "20"))
    PATTERN_CONDITIONED_MIN_EXPECTANCY_R: float = float(os.getenv("PATTERN_CONDITIONED_MIN_EXPECTANCY_R", "0.05"))

    # Prompt 29.5.0d — scenario-pattern calibration. Diagnostic-only: ranks
    # scenario + pattern buckets, calibrates pattern_score/conflict/range filters
    # and proposes a non-operational profile candidate. It never changes paper
    # unlock settings, thresholds, order flow, testnet or live execution.
    SCENARIO_PATTERN_CALIBRATION_ENABLED: bool = os.getenv("SCENARIO_PATTERN_CALIBRATION_ENABLED", "1") == "1"
    SCENARIO_PATTERN_CALIBRATION_HISTORICAL_ENABLED: bool = os.getenv("SCENARIO_PATTERN_CALIBRATION_HISTORICAL_ENABLED", os.getenv("PATTERN_CONDITIONED_HISTORICAL_ENABLED", "1")) == "1"
    SCENARIO_PATTERN_CALIBRATION_REPORT_PATH: str = os.getenv("SCENARIO_PATTERN_CALIBRATION_REPORT_PATH", os.path.join("data", "scenario_pattern_calibration_report.json"))
    SCENARIO_PATTERN_CALIBRATION_SYMBOLS: str = os.getenv("SCENARIO_PATTERN_CALIBRATION_SYMBOLS", PATTERN_CONDITIONED_SYMBOLS)
    SCENARIO_PATTERN_CALIBRATION_MAX_ROWS_PER_ASSET: int = int(os.getenv("SCENARIO_PATTERN_CALIBRATION_MAX_ROWS_PER_ASSET", str(PATTERN_CONDITIONED_MAX_ROWS_PER_ASSET)))
    SCENARIO_PATTERN_CALIBRATION_MIN_WARMUP_ROWS: int = int(os.getenv("SCENARIO_PATTERN_CALIBRATION_MIN_WARMUP_ROWS", str(PATTERN_CONDITIONED_MIN_WARMUP_ROWS)))
    SCENARIO_PATTERN_CALIBRATION_EVAL_STRIDE: int = int(os.getenv("SCENARIO_PATTERN_CALIBRATION_EVAL_STRIDE", str(PATTERN_CONDITIONED_EVAL_STRIDE)))
    SCENARIO_PATTERN_CALIBRATION_HORIZONS: str = os.getenv("SCENARIO_PATTERN_CALIBRATION_HORIZONS", PATTERN_CONDITIONED_HORIZONS)
    SCENARIO_PATTERN_CALIBRATION_STOP_LOSS_PCT: float = float(os.getenv("SCENARIO_PATTERN_CALIBRATION_STOP_LOSS_PCT", str(PATTERN_CONDITIONED_STOP_LOSS_PCT)))
    SCENARIO_PATTERN_CALIBRATION_TP1_PCT: float = float(os.getenv("SCENARIO_PATTERN_CALIBRATION_TP1_PCT", str(PATTERN_CONDITIONED_TP1_PCT)))
    SCENARIO_PATTERN_CALIBRATION_TP2_PCT: float = float(os.getenv("SCENARIO_PATTERN_CALIBRATION_TP2_PCT", str(PATTERN_CONDITIONED_TP2_PCT)))
    SCENARIO_PATTERN_CALIBRATION_SCORE_THRESHOLDS: str = os.getenv("SCENARIO_PATTERN_CALIBRATION_SCORE_THRESHOLDS", "50,55,60,65,70")
    SCENARIO_PATTERN_MIN_BUCKET_CANDIDATES: int = int(os.getenv("SCENARIO_PATTERN_MIN_BUCKET_CANDIDATES", "100"))
    SCENARIO_PATTERN_MIN_PROFILE_CANDIDATES: int = int(os.getenv("SCENARIO_PATTERN_MIN_PROFILE_CANDIDATES", "50"))
    SCENARIO_PATTERN_MIN_BUCKET_EXPECTANCY_R: float = float(os.getenv("SCENARIO_PATTERN_MIN_BUCKET_EXPECTANCY_R", "0.05"))
    SCENARIO_PATTERN_MIN_PROFILE_EXPECTANCY_R: float = float(os.getenv("SCENARIO_PATTERN_MIN_PROFILE_EXPECTANCY_R", "0.10"))
    SCENARIO_PATTERN_MIN_PROFILE_WIN_RATE_PCT: float = float(os.getenv("SCENARIO_PATTERN_MIN_PROFILE_WIN_RATE_PCT", "50.0"))
    SCENARIO_PATTERN_MAX_PROFILE_LOSS_RATE_PCT: float = float(os.getenv("SCENARIO_PATTERN_MAX_PROFILE_LOSS_RATE_PCT", "35.0"))
    SCENARIO_PATTERN_SUPPORT_RANGE_POS_MAX: float = float(os.getenv("SCENARIO_PATTERN_SUPPORT_RANGE_POS_MAX", "0.40"))
    SCENARIO_PATTERN_RESISTANCE_RANGE_POS_MIN: float = float(os.getenv("SCENARIO_PATTERN_RESISTANCE_RANGE_POS_MIN", "0.60"))
    SCENARIO_PATTERN_FOCUS_SYMBOL: str = os.getenv("SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT")
    SCENARIO_PATTERN_FOCUS_BUCKET: str = os.getenv("SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE")
    SCENARIO_PATTERN_CANDIDATE_PROFILE: str = os.getenv("SCENARIO_PATTERN_CANDIDATE_PROFILE", "BTC_BUY_REJECTION_PATTERN_CONFIRMED")

    # Prompt 29.5.0e — liquidity + supply/demand + structure break engine.
    # Diagnostic-only: maps liquidity pools, supply/demand, BOS/CHOCH/MSS and
    # confirmation state. It never changes paper unlock settings, thresholds,
    # order flow, testnet or live execution.
    MARKET_STRUCTURE_MAP_ENABLED: bool = os.getenv("MARKET_STRUCTURE_MAP_ENABLED", "1") == "1"
    MARKET_STRUCTURE_MAP_HISTORICAL_ENABLED: bool = os.getenv("MARKET_STRUCTURE_MAP_HISTORICAL_ENABLED", "1") == "1"
    MARKET_STRUCTURE_MAP_REPORT_PATH: str = os.getenv("MARKET_STRUCTURE_MAP_REPORT_PATH", os.path.join("data", "market_structure_map_report.json"))
    MARKET_STRUCTURE_MAP_SYMBOLS: str = os.getenv("MARKET_STRUCTURE_MAP_SYMBOLS", SCENARIO_PATTERN_CALIBRATION_SYMBOLS)
    MARKET_STRUCTURE_MAP_MAX_ROWS_PER_ASSET: int = int(os.getenv("MARKET_STRUCTURE_MAP_MAX_ROWS_PER_ASSET", str(SCENARIO_PATTERN_CALIBRATION_MAX_ROWS_PER_ASSET)))
    MARKET_STRUCTURE_MAP_MIN_WARMUP_ROWS: int = int(os.getenv("MARKET_STRUCTURE_MAP_MIN_WARMUP_ROWS", str(SCENARIO_PATTERN_CALIBRATION_MIN_WARMUP_ROWS)))
    MARKET_STRUCTURE_MAP_EVAL_STRIDE: int = int(os.getenv("MARKET_STRUCTURE_MAP_EVAL_STRIDE", "25"))
    MARKET_STRUCTURE_MAP_MAX_SNAPSHOTS_PER_ASSET: int = int(os.getenv("MARKET_STRUCTURE_MAP_MAX_SNAPSHOTS_PER_ASSET", "160"))
    MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS: int = int(os.getenv("MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS", "900"))
    MARKET_STRUCTURE_MAP_SWING_LEFT: int = int(os.getenv("MARKET_STRUCTURE_MAP_SWING_LEFT", "3"))
    MARKET_STRUCTURE_MAP_SWING_RIGHT: int = int(os.getenv("MARKET_STRUCTURE_MAP_SWING_RIGHT", "2"))
    MARKET_STRUCTURE_MAP_RECENT_SWING_LOOKBACK: int = int(os.getenv("MARKET_STRUCTURE_MAP_RECENT_SWING_LOOKBACK", "12"))
    MARKET_STRUCTURE_MAP_EQUAL_LEVEL_TOLERANCE_PCT: float = float(os.getenv("MARKET_STRUCTURE_MAP_EQUAL_LEVEL_TOLERANCE_PCT", "0.0015"))
    MARKET_STRUCTURE_MAP_LIQUIDITY_NEAR_PCT: float = float(os.getenv("MARKET_STRUCTURE_MAP_LIQUIDITY_NEAR_PCT", "0.0040"))
    MARKET_STRUCTURE_MAP_ZONE_ATR_MULT: float = float(os.getenv("MARKET_STRUCTURE_MAP_ZONE_ATR_MULT", "0.45"))
    MARKET_STRUCTURE_MAP_RETEST_TOLERANCE_PCT: float = float(os.getenv("MARKET_STRUCTURE_MAP_RETEST_TOLERANCE_PCT", "0.0020"))
    MARKET_STRUCTURE_MAP_CONFIRMATION_BODY_RATIO: float = float(os.getenv("MARKET_STRUCTURE_MAP_CONFIRMATION_BODY_RATIO", "0.35"))
    MARKET_STRUCTURE_MAP_CONFIRMATION_CLOSE_BUFFER_PCT: float = float(os.getenv("MARKET_STRUCTURE_MAP_CONFIRMATION_CLOSE_BUFFER_PCT", "0.0005"))
    MARKET_STRUCTURE_MAP_FOCUS_SYMBOL: str = os.getenv("MARKET_STRUCTURE_MAP_FOCUS_SYMBOL", "BTC/USDT")


    # Cost-aware meta-labeling diagnostics.  By default this is diagnostic-only:
    # it reports net expectancy after estimated execution friction without changing
    # live/backtest decisions.  Set META_COST_AWARE_GATING=1 only after validating
    # the recommended thresholds with walk-forward/backtest.
    META_COST_AWARE_ENABLED: bool = os.getenv("META_COST_AWARE_ENABLED", "1") == "1"
    META_COST_AWARE_GATING: bool = os.getenv("META_COST_AWARE_GATING", "0") == "1"
    META_MIN_NET_EDGE_R: float = float(os.getenv("META_MIN_NET_EDGE_R", "0.00"))
    META_MAX_COST_TO_EDGE_RATIO: float = float(os.getenv("META_MAX_COST_TO_EDGE_RATIO", "1.00"))
    COST_AWARE_REPORT_PATH: str = os.getenv("COST_AWARE_REPORT_PATH", os.path.join("data", "cost_aware_threshold_report.json"))

    # Adaptive regime threshold diagnostics. Diagnostic-only by default.
    # These settings analyze regime-specific probability/quality gates without
    # changing trading decisions unless explicitly wired and validated.
    ADAPTIVE_REGIME_THRESHOLDS_ENABLED: bool = os.getenv("ADAPTIVE_REGIME_THRESHOLDS_ENABLED", "1") == "1"
    ADAPTIVE_REGIME_THRESHOLDS_GATING: bool = os.getenv("ADAPTIVE_REGIME_THRESHOLDS_GATING", "0") == "1"
    ADAPTIVE_REGIME_MIN_TRADES: int = int(os.getenv("ADAPTIVE_REGIME_MIN_TRADES", "3"))
    ADAPTIVE_REGIME_THRESHOLD_REPORT_PATH: str = os.getenv("ADAPTIVE_REGIME_THRESHOLD_REPORT_PATH", os.path.join("data", "adaptive_regime_threshold_report.json"))

    # Prompt 27 — market-structure setup engine
    SETUP_STRUCTURE_FEATURES_ENABLED: bool = os.getenv("SETUP_STRUCTURE_FEATURES_ENABLED", "1") == "1"
    SETUP_STRUCTURE_GATING: bool = os.getenv("SETUP_STRUCTURE_GATING", "0") == "1"
    SETUP_STRUCTURE_MIN_SCORE: float = float(os.getenv("SETUP_STRUCTURE_MIN_SCORE", "20.0"))
    SETUP_STRUCTURE_REPORT_PATH: str = os.getenv("SETUP_STRUCTURE_REPORT_PATH", os.path.join("data", "setup_engine_report.json"))

    # Prompt 28.1 — archetype activation controls.
    # These do not create signals; they only classify existing technical
    # candidates with less mean-reversion bias when a more specific structural
    # setup is close enough to the winning score.
    SETUP_ARCHETYPE_MIN_SCORE: float = float(os.getenv("SETUP_ARCHETYPE_MIN_SCORE", "32.0"))
    SETUP_ARCHETYPE_SPECIFICITY_MARGIN: float = float(os.getenv("SETUP_ARCHETYPE_SPECIFICITY_MARGIN", "12.0"))
    SETUP_HTF_RETURN_EPS: float = float(os.getenv("SETUP_HTF_RETURN_EPS", "0.0005"))
    SETUP_VOL_COMPRESSION_THRESHOLD: float = float(os.getenv("SETUP_VOL_COMPRESSION_THRESHOLD", "0.95"))
    SETUP_SWEEP_SCORE_MIN: float = float(os.getenv("SETUP_SWEEP_SCORE_MIN", "0.0001"))

    # Prompt 28.2 — runtime market-structure propagation + fallback controls.
    BACKTEST_MARKET_STRUCTURE_ENRICHMENT: bool = os.getenv("BACKTEST_MARKET_STRUCTURE_ENRICHMENT", "1") == "1"
    BACKTEST_MARKET_STRUCTURE_STRICT_AUDIT: bool = os.getenv("BACKTEST_MARKET_STRUCTURE_STRICT_AUDIT", "0") == "1"
    SETUP_MARKET_STRUCTURE_AUDIT: bool = os.getenv("SETUP_MARKET_STRUCTURE_AUDIT", "1") == "1"
    SETUP_MR_REQUIRE_CONFIRMATION: bool = os.getenv("SETUP_MR_REQUIRE_CONFIRMATION", "1") == "1"
    SETUP_MR_MIN_STRUCTURE_SCORE: float = float(os.getenv("SETUP_MR_MIN_STRUCTURE_SCORE", "52.0"))
    SETUP_MR_FALLBACK_EDGE_PENALTY_R: float = float(os.getenv("SETUP_MR_FALLBACK_EDGE_PENALTY_R", "0.08"))
    SETUP_MR_MISSING_FEATURE_PENALTY: float = float(os.getenv("SETUP_MR_MISSING_FEATURE_PENALTY", "10.0"))


    # Prompt 28.4: archetype-conditioned gating.  A single global meta
    # threshold made the framework accept 100% of technical candidates once
    # runtime market-structure features were propagated.  These conservative
    # per-archetype gates keep the setup engine from treating all structure
    # families as equally reliable before realized validation exists.
    SETUP_ARCHETYPE_GATING_ENABLED: bool = os.getenv("SETUP_ARCHETYPE_GATING_ENABLED", "1") == "1"
    SETUP_ACCEPTANCE_RATE_GUARDRAIL: float = float(os.getenv("SETUP_ACCEPTANCE_RATE_GUARDRAIL", "0.80"))
    SETUP_UNVALIDATED_ARCHETYPE_EDGE_PENALTY_R: float = float(os.getenv("SETUP_UNVALIDATED_ARCHETYPE_EDGE_PENALTY_R", "0.05"))

    SETUP_HTF_MIN_PROB: float = float(os.getenv("SETUP_HTF_MIN_PROB", "50.0"))
    SETUP_HTF_MIN_QUALITY: float = float(os.getenv("SETUP_HTF_MIN_QUALITY", "58.0"))
    SETUP_HTF_MIN_STRUCTURE: float = float(os.getenv("SETUP_HTF_MIN_STRUCTURE", "62.0"))
    SETUP_HTF_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_HTF_MIN_NET_EDGE_R", "0.10"))

    SETUP_VOL_BREAKOUT_MIN_PROB: float = float(os.getenv("SETUP_VOL_BREAKOUT_MIN_PROB", "52.0"))
    SETUP_VOL_BREAKOUT_MIN_QUALITY: float = float(os.getenv("SETUP_VOL_BREAKOUT_MIN_QUALITY", "62.0"))
    SETUP_VOL_BREAKOUT_MIN_STRUCTURE: float = float(os.getenv("SETUP_VOL_BREAKOUT_MIN_STRUCTURE", "65.0"))
    SETUP_VOL_BREAKOUT_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_VOL_BREAKOUT_MIN_NET_EDGE_R", "0.15"))

    SETUP_SWEEP_MIN_PROB: float = float(os.getenv("SETUP_SWEEP_MIN_PROB", "52.0"))
    SETUP_SWEEP_MIN_QUALITY: float = float(os.getenv("SETUP_SWEEP_MIN_QUALITY", "60.0"))
    SETUP_SWEEP_MIN_STRUCTURE: float = float(os.getenv("SETUP_SWEEP_MIN_STRUCTURE", "62.0"))
    SETUP_SWEEP_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_SWEEP_MIN_NET_EDGE_R", "0.12"))

    SETUP_SESSION_MIN_PROB: float = float(os.getenv("SETUP_SESSION_MIN_PROB", "54.0"))
    SETUP_SESSION_MIN_QUALITY: float = float(os.getenv("SETUP_SESSION_MIN_QUALITY", "62.0"))
    SETUP_SESSION_MIN_STRUCTURE: float = float(os.getenv("SETUP_SESSION_MIN_STRUCTURE", "65.0"))
    SETUP_SESSION_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_SESSION_MIN_NET_EDGE_R", "0.15"))

    SETUP_MR_MIN_PROB: float = float(os.getenv("SETUP_MR_MIN_PROB", "55.0"))
    SETUP_MR_MIN_QUALITY: float = float(os.getenv("SETUP_MR_MIN_QUALITY", "60.0"))
    SETUP_MR_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_MR_MIN_NET_EDGE_R", "0.18"))

    # Prompt 28.6: realized-feedback safety controls.  The 50k-candle run
    # identified HTF_ALIGNED_PULLBACK as the only realized traded archetype and
    # it was materially negative.  It is disabled by default until revalidated;
    # set SETUP_DISABLED_ARCHETYPES="" to re-enable it for research runs.
    SETUP_DISABLED_ARCHETYPES: str = os.getenv("SETUP_DISABLED_ARCHETYPES", "HTF_ALIGNED_PULLBACK")
    SETUP_AUTO_DISABLE_NEGATIVE_ARCHETYPES: bool = os.getenv("SETUP_AUTO_DISABLE_NEGATIVE_ARCHETYPES", "1") == "1"
    SETUP_NEGATIVE_ARCHETYPE_MIN_TRADES: int = int(os.getenv("SETUP_NEGATIVE_ARCHETYPE_MIN_TRADES", "5"))
    SETUP_NEGATIVE_ARCHETYPE_AVG_R_MAX: float = float(os.getenv("SETUP_NEGATIVE_ARCHETYPE_AVG_R_MAX", "-0.05"))
    SETUP_NEGATIVE_ARCHETYPE_REPORT_PATH: str = os.getenv("SETUP_NEGATIVE_ARCHETYPE_REPORT_PATH", os.path.join("data", "archetype_performance_report.json"))

    # Stop generating new pending triggers while the risk engine is already in
    # daily-loss block.  This keeps the risk engine from becoming a strategic
    # filter and avoids hundreds of blocked sizing snapshots.
    PRE_RISK_THROTTLE_ON_DAILY_BLOCK: bool = os.getenv("PRE_RISK_THROTTLE_ON_DAILY_BLOCK", "1") == "1"

    # Keep the global trained registry active when the current bar is outside a
    # WF test fold in evaluation-only mode.
    WF_KEEP_GLOBAL_MODEL_WHEN_NO_ACTIVE_FOLD: bool = os.getenv("WF_KEEP_GLOBAL_MODEL_WHEN_NO_ACTIVE_FOLD", "1") == "1"
    AI_PREDICTION_AUDIT: bool = os.getenv("AI_PREDICTION_AUDIT", "1") == "1"


    # Prompt 28.7: edge stability validation and paper-trading readiness guardrails.
    EDGE_STABILITY_MIN_TRADES_PER_ARCHETYPE: int = int(os.getenv("EDGE_STABILITY_MIN_TRADES_PER_ARCHETYPE", "20"))
    EDGE_STABILITY_MIN_AVG_R: float = float(os.getenv("EDGE_STABILITY_MIN_AVG_R", "0.05"))
    EDGE_STABILITY_LOW_ATR_PCT: float = float(os.getenv("EDGE_STABILITY_LOW_ATR_PCT", "0.30"))
    EDGE_STABILITY_HIGH_ATR_PCT: float = float(os.getenv("EDGE_STABILITY_HIGH_ATR_PCT", "0.75"))
    PAPER_READY_MIN_TRADES: int = int(os.getenv("PAPER_READY_MIN_TRADES", "30"))
    PAPER_READY_MIN_ARCHETYPE_TRADES: int = int(os.getenv("PAPER_READY_MIN_ARCHETYPE_TRADES", "10"))
    PAPER_READY_MIN_POSITIVE_ARCHETYPES: int = int(os.getenv("PAPER_READY_MIN_POSITIVE_ARCHETYPES", "2"))
    PAPER_READY_MAX_DD_PCT: float = float(os.getenv("PAPER_READY_MAX_DD_PCT", "12.0"))
    PAPER_READY_MIN_NET_PCT: float = float(os.getenv("PAPER_READY_MIN_NET_PCT", "0.0"))
    PAPER_READY_MAX_META_ACCEPTANCE_RATE_PCT: float = float(os.getenv("PAPER_READY_MAX_META_ACCEPTANCE_RATE_PCT", "5.0"))
    PAPER_READY_MIN_WF_FOLDS: int = int(os.getenv("PAPER_READY_MIN_WF_FOLDS", "20"))


    # Prompt 28.8.1: runtime profiling + fast research mode.
    RUNTIME_PROFILE_ENABLED: bool = os.getenv("RUNTIME_PROFILE_ENABLED", "1") == "1"
    RUNTIME_PROFILE_REPORT_PATH: str = os.getenv("RUNTIME_PROFILE_REPORT_PATH", os.path.join("data", "runtime_profile_report.json"))
    RUNTIME_PROFILER = None
    BACKTEST_FAST_MODE: bool = os.getenv("BACKTEST_FAST_MODE", "0") == "1"
    BACKTEST_SAVE_CHARTS: bool = os.getenv("BACKTEST_SAVE_CHARTS", "1") == "1"
    BACKTEST_RISK_PROFILE: str = os.getenv("BACKTEST_RISK_PROFILE", "ALL").upper()
    BACKTEST_PRINT_WF_TIMELINE: bool = os.getenv("BACKTEST_PRINT_WF_TIMELINE", "1") == "1"
    BACKTEST_PRINT_WF_FOLD_TABLE: bool = os.getenv("BACKTEST_PRINT_WF_FOLD_TABLE", "1") == "1"
    BACKTEST_PRINT_WF_MODEL_LINES: bool = os.getenv("BACKTEST_PRINT_WF_MODEL_LINES", "1") == "1"

    # Prompt 28.8.3: avoid expensive per-fold local dataset reconstruction
    # during evaluation-only backtests. In WF_EVALUATION_ONLY mode the fold
    # state is only used to route the already-trained global model, so we can
    # snapshot the global registry once per fold from split metadata.
    WF_FAST_EVAL_ONLY_ROUTING_CACHE: bool = os.getenv("WF_FAST_EVAL_ONLY_ROUTING_CACHE", "1") == "1"

    # Prompt 28.11: asset/archetype-specific cost robustness gates.
    # Defaults reflect the 28.10 cost-stress matrix: BTC/BNB are the most robust;
    # ETH/SOL retain mean reversion but liquidity sweeps are blocked under stressed
    # cost models; XRP remains research-only until revalidated.
    ASSET_ARCHETYPE_GATING_ENABLED: bool = os.getenv("ASSET_ARCHETYPE_GATING_ENABLED", "1") == "1"
    PAPER_ASSET_UNIVERSE: str = os.getenv("PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT")
    PAPER_EXCLUDED_ASSETS: str = os.getenv("PAPER_EXCLUDED_ASSETS", "XRP/USDT")
    PAPER_ASSET_UNIVERSE_ENFORCED: bool = os.getenv("PAPER_ASSET_UNIVERSE_ENFORCED", "0") == "1"
    COST_ROBUSTNESS_GATE_COST_MODELS: str = os.getenv("COST_ROBUSTNESS_GATE_COST_MODELS", "conservative,severe")
    COST_ROBUSTNESS_DISABLED_ASSET_ARCHETYPES: str = os.getenv(
        "COST_ROBUSTNESS_DISABLED_ASSET_ARCHETYPES",
        "ETH/USDT:LIQUIDITY_SWEEP_REVERSAL|SOL/USDT:LIQUIDITY_SWEEP_REVERSAL|XRP/USDT:LIQUIDITY_SWEEP_REVERSAL",
    )

    # Prompt 28.8.1: timeframe/archetype research controls.  The 5m run showed
    # VOL_COMPRESSION_BREAKOUT slightly negative on realized R with very low sample.
    SETUP_DISABLED_ARCHETYPES_5M: str = os.getenv("SETUP_DISABLED_ARCHETYPES_5M", "VOL_COMPRESSION_BREAKOUT")
    SETUP_DISABLED_ARCHETYPES_3M: str = os.getenv("SETUP_DISABLED_ARCHETYPES_3M", "VOL_COMPRESSION_BREAKOUT")
    SETUP_5M_MR_MIN_PROB: float = float(os.getenv("SETUP_5M_MR_MIN_PROB", "52.0"))
    SETUP_5M_MR_MIN_NET_EDGE_R: float = float(os.getenv("SETUP_5M_MR_MIN_NET_EDGE_R", "0.15"))

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