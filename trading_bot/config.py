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
    TELEGRAM_POSITION_DASHBOARD_SINGLE_MESSAGE: bool = os.getenv("TELEGRAM_POSITION_DASHBOARD_SINGLE_MESSAGE", "1") == "1"
    TELEGRAM_POSITION_DASHBOARD_UPDATE_SECONDS: float = float(os.getenv("TELEGRAM_POSITION_DASHBOARD_UPDATE_SECONDS", "20"))
    TELEGRAM_POSITION_DASHBOARD_BAR_WIDTH: int = int(os.getenv("TELEGRAM_POSITION_DASHBOARD_BAR_WIDTH", "20"))
    TELEGRAM_POSITION_DASHBOARD_SEND_CLOSE_SUMMARY: bool = os.getenv("TELEGRAM_POSITION_DASHBOARD_SEND_CLOSE_SUMMARY", "1") == "1"


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

    # Prompt 29.5.0f — calibrated scenario-pattern-structure shadow review.
    # Diagnostic-only: compares scenario+pattern calibrated candidates against
    # liquidity/supply-demand/structure filters. It never changes paper unlock,
    # thresholds, risk, order flow, testnet or live execution.
    CALIBRATED_STRUCTURE_SHADOW_ENABLED: bool = os.getenv("CALIBRATED_STRUCTURE_SHADOW_ENABLED", "1") == "1"
    CALIBRATED_STRUCTURE_SHADOW_HISTORICAL_ENABLED: bool = os.getenv("CALIBRATED_STRUCTURE_SHADOW_HISTORICAL_ENABLED", "1") == "1"
    CALIBRATED_STRUCTURE_SHADOW_REPORT_PATH: str = os.getenv("CALIBRATED_STRUCTURE_SHADOW_REPORT_PATH", os.path.join("data", "calibrated_structure_shadow_report.json"))
    CALIBRATED_STRUCTURE_SHADOW_SYMBOLS: str = os.getenv("CALIBRATED_STRUCTURE_SHADOW_SYMBOLS", SCENARIO_PATTERN_CALIBRATION_SYMBOLS)
    CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET", str(SCENARIO_PATTERN_CALIBRATION_MAX_ROWS_PER_ASSET)))
    CALIBRATED_STRUCTURE_SHADOW_MIN_WARMUP_ROWS: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MIN_WARMUP_ROWS", str(SCENARIO_PATTERN_CALIBRATION_MIN_WARMUP_ROWS)))
    CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE", "3"))
    CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", "220"))
    CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS", str(MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS)))
    CALIBRATED_STRUCTURE_SHADOW_SCORE_THRESHOLDS: str = os.getenv("CALIBRATED_STRUCTURE_SHADOW_SCORE_THRESHOLDS", "60,65,70")
    CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES: int = int(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES", "50"))
    CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R: float = float(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R", "0.10"))
    CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT: float = float(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT", "52.0"))
    CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT: float = float(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT", "45.0"))
    CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT", "60.0"))

    # Prompt 29.5.0g — structure filter diagnostics / confirmation quality audit.
    # Diagnostic-only: audits demand/supply/liquidity/BOS/CHOCH/MSS confirmation
    # quality and failure modes after 29.5.0f. It never changes paper unlock,
    # thresholds, risk, order flow, testnet or live execution.
    STRUCTURE_FILTER_DIAGNOSTICS_ENABLED: bool = os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_ENABLED", "1") == "1"
    STRUCTURE_FILTER_DIAGNOSTICS_HISTORICAL_ENABLED: bool = os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_HISTORICAL_ENABLED", "1") == "1"
    STRUCTURE_FILTER_DIAGNOSTICS_REPORT_PATH: str = os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_REPORT_PATH", os.path.join("data", "structure_filter_diagnostics_report.json"))
    STRUCTURE_FILTER_DIAGNOSTICS_MAX_ROWS_PER_ASSET: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MAX_ROWS_PER_ASSET", str(CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET)))
    STRUCTURE_FILTER_DIAGNOSTICS_EVAL_STRIDE: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_EVAL_STRIDE", str(CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE)))
    STRUCTURE_FILTER_DIAGNOSTICS_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    STRUCTURE_FILTER_DIAGNOSTICS_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_STRUCTURE_WINDOW_ROWS", str(CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS)))
    STRUCTURE_FILTER_DIAGNOSTICS_MIN_COMPONENT_CANDIDATES: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MIN_COMPONENT_CANDIDATES", "20"))
    STRUCTURE_FILTER_DIAGNOSTICS_MIN_VARIANT_CANDIDATES: int = int(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MIN_VARIANT_CANDIDATES", str(CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES)))
    STRUCTURE_FILTER_DIAGNOSTICS_MIN_EXPECTANCY_R: float = float(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MIN_EXPECTANCY_R", str(CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R)))
    STRUCTURE_FILTER_DIAGNOSTICS_MIN_WIN_RATE_PCT: float = float(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MIN_WIN_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT)))
    STRUCTURE_FILTER_DIAGNOSTICS_MAX_LOSS_RATE_PCT: float = float(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MAX_LOSS_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT)))
    STRUCTURE_FILTER_DIAGNOSTICS_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("STRUCTURE_FILTER_DIAGNOSTICS_MAX_TIME_EXIT_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT)))

    STRUCTURE_CONTEXT_REPAIR_ENABLED: bool = os.getenv("STRUCTURE_CONTEXT_REPAIR_ENABLED", "1") == "1"
    STRUCTURE_CONTEXT_REPAIR_HISTORICAL_ENABLED: bool = os.getenv("STRUCTURE_CONTEXT_REPAIR_HISTORICAL_ENABLED", "1") == "1"
    STRUCTURE_CONTEXT_REPAIR_REPORT_PATH: str = os.getenv("STRUCTURE_CONTEXT_REPAIR_REPORT_PATH", os.path.join("data", "structure_context_repair_report.json"))
    STRUCTURE_CONTEXT_REPAIR_MAX_ROWS_PER_ASSET: int = int(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAX_ROWS_PER_ASSET", str(CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET)))
    STRUCTURE_CONTEXT_REPAIR_EVAL_STRIDE: int = int(os.getenv("STRUCTURE_CONTEXT_REPAIR_EVAL_STRIDE", str(CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE)))
    STRUCTURE_CONTEXT_REPAIR_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    STRUCTURE_CONTEXT_REPAIR_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("STRUCTURE_CONTEXT_REPAIR_STRUCTURE_WINDOW_ROWS", str(CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS)))
    STRUCTURE_CONTEXT_REPAIR_MIN_VARIANT_CANDIDATES: int = int(os.getenv("STRUCTURE_CONTEXT_REPAIR_MIN_VARIANT_CANDIDATES", str(CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES)))
    STRUCTURE_CONTEXT_REPAIR_MIN_EXPECTANCY_R: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MIN_EXPECTANCY_R", str(CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R)))
    STRUCTURE_CONTEXT_REPAIR_MIN_WIN_RATE_PCT: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MIN_WIN_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT)))
    STRUCTURE_CONTEXT_REPAIR_MAX_LOSS_RATE_PCT: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAX_LOSS_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT)))
    STRUCTURE_CONTEXT_REPAIR_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAX_TIME_EXIT_RATE_PCT", str(CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT)))
    STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MIN", "65.0"))
    STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MAX", "79.999"))
    STRUCTURE_CONTEXT_REPAIR_SCORE_THRESHOLDS: str = os.getenv("STRUCTURE_CONTEXT_REPAIR_SCORE_THRESHOLDS", CALIBRATED_STRUCTURE_SHADOW_SCORE_THRESHOLDS)

    # Prompt 29.5.0i — repaired structure shadow validation / MAP_SCORE_65_79 and BOS audit.
    # Diagnostic-only: validates repaired CONTEXT/CONFIRMATION, MAP_SCORE_65_79,
    # BOS, WAIT watchlist and NO_STRUCTURE anomaly after 29.5.0h. It never
    # changes paper unlock, thresholds, risk, order flow, testnet or live execution.
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED: bool = os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED", "1") == "1"
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_HISTORICAL_ENABLED: bool = os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_HISTORICAL_ENABLED", "1") == "1"
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_REPORT_PATH: str = os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_REPORT_PATH", os.path.join("data", "repaired_structure_shadow_validation_report.json"))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_ROWS_PER_ASSET: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_ROWS_PER_ASSET", str(STRUCTURE_CONTEXT_REPAIR_MAX_ROWS_PER_ASSET)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_EVAL_STRIDE: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_EVAL_STRIDE", str(STRUCTURE_CONTEXT_REPAIR_EVAL_STRIDE)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(STRUCTURE_CONTEXT_REPAIR_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_STRUCTURE_WINDOW_ROWS", str(STRUCTURE_CONTEXT_REPAIR_STRUCTURE_WINDOW_ROWS)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_VARIANT_CANDIDATES: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_VARIANT_CANDIDATES", str(STRUCTURE_CONTEXT_REPAIR_MIN_VARIANT_CANDIDATES)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_COMPONENT_CANDIDATES: int = int(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_COMPONENT_CANDIDATES", "10"))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_EXPECTANCY_R: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_EXPECTANCY_R", str(STRUCTURE_CONTEXT_REPAIR_MIN_EXPECTANCY_R)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_WIN_RATE_PCT: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_WIN_RATE_PCT", str(STRUCTURE_CONTEXT_REPAIR_MIN_WIN_RATE_PCT)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_LOSS_RATE_PCT: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_LOSS_RATE_PCT", str(STRUCTURE_CONTEXT_REPAIR_MAX_LOSS_RATE_PCT)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_TIME_EXIT_RATE_PCT", str(STRUCTURE_CONTEXT_REPAIR_MAX_TIME_EXIT_RATE_PCT)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MIN", str(STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MIN)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MAX", str(STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MAX)))
    REPAIRED_STRUCTURE_SHADOW_VALIDATION_SCORE_THRESHOLDS: str = os.getenv("REPAIRED_STRUCTURE_SHADOW_VALIDATION_SCORE_THRESHOLDS", STRUCTURE_CONTEXT_REPAIR_SCORE_THRESHOLDS)

    INDEPENDENT_REPAIRED_VALIDATION_ENABLED: bool = os.getenv("INDEPENDENT_REPAIRED_VALIDATION_ENABLED", "1") == "1"
    INDEPENDENT_REPAIRED_VALIDATION_HISTORICAL_ENABLED: bool = os.getenv("INDEPENDENT_REPAIRED_VALIDATION_HISTORICAL_ENABLED", "1") == "1"
    INDEPENDENT_REPAIRED_VALIDATION_REPORT_PATH: str = os.getenv("INDEPENDENT_REPAIRED_VALIDATION_REPORT_PATH", os.path.join("data", "independent_repaired_validation_report.json"))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_ROWS_PER_ASSET: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_ROWS_PER_ASSET", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_ROWS_PER_ASSET)))
    INDEPENDENT_REPAIRED_VALIDATION_EVAL_STRIDE: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_EVAL_STRIDE", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_EVAL_STRIDE)))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    INDEPENDENT_REPAIRED_VALIDATION_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_STRUCTURE_WINDOW_ROWS", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_STRUCTURE_WINDOW_ROWS)))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_VARIANT_CANDIDATES: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_VARIANT_CANDIDATES", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_VARIANT_CANDIDATES)))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_COMPONENT_CANDIDATES: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_COMPONENT_CANDIDATES", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_COMPONENT_CANDIDATES)))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_FOLD_CANDIDATES: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_FOLD_CANDIDATES", "10"))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_CANDIDATES: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_CANDIDATES", "15"))
    INDEPENDENT_REPAIRED_VALIDATION_FOLD_COUNT: int = int(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_FOLD_COUNT", "3"))
    INDEPENDENT_REPAIRED_VALIDATION_HOLDOUT_FRACTION: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_HOLDOUT_FRACTION", "0.35"))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_EXPECTANCY_R: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_EXPECTANCY_R", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_EXPECTANCY_R)))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_WIN_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_WIN_RATE_PCT", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_WIN_RATE_PCT)))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_LOSS_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_LOSS_RATE_PCT", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_LOSS_RATE_PCT)))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_TIME_EXIT_RATE_PCT", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_TIME_EXIT_RATE_PCT)))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_EXPECTANCY_R: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_EXPECTANCY_R", "0.05"))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_WIN_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_WIN_RATE_PCT", "52.0"))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_HOLDOUT_LOSS_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_HOLDOUT_LOSS_RATE_PCT", "45.0"))
    INDEPENDENT_REPAIRED_VALIDATION_MIN_POSITIVE_FOLD_RATE_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MIN_POSITIVE_FOLD_RATE_PCT", "66.67"))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_ASSET_CONCENTRATION_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_ASSET_CONCENTRATION_PCT", "70.0"))
    INDEPENDENT_REPAIRED_VALIDATION_MAX_SIDE_CONCENTRATION_PCT: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAX_SIDE_CONCENTRATION_PCT", "80.0"))
    INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MIN", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MIN)))
    INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MAX", str(REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MAX)))

    # Prompt 29.4.4c — paper unlock profile refinement design.
    # Diagnostic-only: drafts MAP_SCORE_65_79_REPAIRED_STABILITY_V1 after
    # 29.5.0j. It never enables orders, paper unlock, testnet or live.
    PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED: bool = os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED", "1") == "1"
    PAPER_UNLOCK_PROFILE_REFINEMENT_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_HISTORICAL_ENABLED", "1") == "1"
    PAPER_UNLOCK_PROFILE_REFINEMENT_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_REPORT_PATH", os.path.join("data", "paper_unlock_profile_refinement_report.json"))
    PAPER_UNLOCK_PROFILE_REFINEMENT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ROWS_PER_ASSET", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_EVAL_STRIDE", str(INDEPENDENT_REPAIRED_VALIDATION_EVAL_STRIDE)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_STRUCTURE_WINDOW_ROWS", str(INDEPENDENT_REPAIRED_VALIDATION_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_VARIANT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_VARIANT_CANDIDATES", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_VARIANT_CANDIDATES)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_COMPONENT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_COMPONENT_CANDIDATES", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_COMPONENT_CANDIDATES)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_FOLD_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_FOLD_CANDIDATES", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_FOLD_CANDIDATES)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_CANDIDATES", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_CANDIDATES)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_FOLD_COUNT: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_FOLD_COUNT", str(INDEPENDENT_REPAIRED_VALIDATION_FOLD_COUNT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_HOLDOUT_FRACTION: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_HOLDOUT_FRACTION", str(INDEPENDENT_REPAIRED_VALIDATION_HOLDOUT_FRACTION)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_EXPECTANCY_R", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_EXPECTANCY_R)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_WIN_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_WIN_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_WIN_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_LOSS_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_LOSS_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_TIME_EXIT_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_EXPECTANCY_R", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_EXPECTANCY_R)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_WIN_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_WIN_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_WIN_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_HOLDOUT_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_HOLDOUT_LOSS_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_HOLDOUT_LOSS_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_POSITIVE_FOLD_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_POSITIVE_FOLD_RATE_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MIN_POSITIVE_FOLD_RATE_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ASSET_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ASSET_CONCENTRATION_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_ASSET_CONCENTRATION_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_SIDE_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_SIDE_CONCENTRATION_PCT", str(INDEPENDENT_REPAIRED_VALIDATION_MAX_SIDE_CONCENTRATION_PCT)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MIN", str(INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MAX", str(INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_PROFILE_REFINEMENT_REQUIRE_STABILITY_CANDIDATE: bool = os.getenv("PAPER_UNLOCK_PROFILE_REFINEMENT_REQUIRE_STABILITY_CANDIDATE", "1") == "1"


    # Prompt 29.4.4d — calibrated paper-only unlock experiment design.
    # Diagnostic-only: drafts a future paper-only experiment plan after 29.4.4c.
    # It never enables orders, paper unlock experiment execution, testnet or live.
    PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_DESIGN_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_HISTORICAL_ENABLED", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_DESIGN_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_REPORT_PATH", os.path.join("data", "paper_unlock_experiment_design_report.json"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_PROFILE_NAME", PAPER_UNLOCK_PROFILE_REFINEMENT_PROFILE_NAME)
    PAPER_UNLOCK_EXPERIMENT_DESIGN_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_ROWS_PER_ASSET", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_EVAL_STRIDE", str(PAPER_UNLOCK_PROFILE_REFINEMENT_EVAL_STRIDE)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_STRUCTURE_WINDOW_ROWS", str(PAPER_UNLOCK_PROFILE_REFINEMENT_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_VARIANT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_VARIANT_CANDIDATES", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_VARIANT_CANDIDATES)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_COMPONENT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_COMPONENT_CANDIDATES", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_COMPONENT_CANDIDATES)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_FOLD_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_FOLD_CANDIDATES", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_FOLD_CANDIDATES)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_HOLDOUT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_HOLDOUT_CANDIDATES", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_CANDIDATES)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_FOLD_COUNT: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_FOLD_COUNT", str(PAPER_UNLOCK_PROFILE_REFINEMENT_FOLD_COUNT)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_HOLDOUT_FRACTION: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_HOLDOUT_FRACTION", str(PAPER_UNLOCK_PROFILE_REFINEMENT_HOLDOUT_FRACTION)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_EXPECTANCY_R", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_EXPECTANCY_R)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_WIN_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_WIN_RATE_PCT", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_WIN_RATE_PCT)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_LOSS_RATE_PCT", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_LOSS_RATE_PCT)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_TIME_EXIT_RATE_PCT", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MIN", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MAX", str(PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_POSITIONS", str(PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_MAX_POSITIONS)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_RISK_PER_TRADE_PCT", str(PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_RISK_PER_TRADE_PCT)))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_DAILY_ENTRIES", "1"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_WEEKLY_ENTRIES", "5"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_RUNTIME_SHADOW_MIN_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_RUNTIME_SHADOW_MIN_CANDIDATES", "20"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_RUNTIME_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_RUNTIME_EXPECTANCY_R", "0.05"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_RUNTIME_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_RUNTIME_LOSS_RATE_PCT", "50.0"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_DRAWDOWN_PCT", "1.0"))
    PAPER_UNLOCK_EXPERIMENT_DESIGN_REQUIRE_PROFILE_READY: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_DESIGN_REQUIRE_PROFILE_READY", "1") == "1"

    # Prompt 29.4.4e — paper-only shadow experiment dry-run harness.
    # Diagnostic-only: simulates the designed paper-only experiment as shadow
    # events/rate limits/abort checks. It never enables paper orders, testnet or live.
    PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED", "1") == "1"
    PAPER_UNLOCK_SHADOW_DRY_RUN_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_HISTORICAL_ENABLED", "1") == "1"
    PAPER_UNLOCK_SHADOW_DRY_RUN_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_REPORT_PATH", os.path.join("data", "paper_unlock_shadow_dry_run_report.json"))
    PAPER_UNLOCK_SHADOW_DRY_RUN_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_PROFILE_NAME", PAPER_UNLOCK_EXPERIMENT_DESIGN_PROFILE_NAME)
    PAPER_UNLOCK_SHADOW_DRY_RUN_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_EXPERIMENT_NAME", PAPER_UNLOCK_EXPERIMENT_DESIGN_EXPERIMENT_NAME)
    PAPER_UNLOCK_SHADOW_DRY_RUN_HARNESS_NAME: str = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_HARNESS_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_DRY_RUN")
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_ROWS_PER_ASSET", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_EVAL_STRIDE", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_EVAL_STRIDE)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_STRUCTURE_WINDOW_ROWS", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_VARIANT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_VARIANT_CANDIDATES", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_VARIANT_CANDIDATES)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_ENTRIES", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_RUNTIME_SHADOW_MIN_CANDIDATES)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_EXPECTANCY_R", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_RUNTIME_EXPECTANCY_R)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_LOSS_RATE_PCT", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_RUNTIME_LOSS_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_TIME_EXIT_RATE_PCT", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MIN", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MAX", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_POSITIONS", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_POSITIONS)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_RISK_PER_TRADE_PCT", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_RISK_PER_TRADE_PCT)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_DAILY_ENTRIES", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_DAILY_ENTRIES)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_WEEKLY_ENTRIES", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_WEEKLY_ENTRIES)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_CONSECUTIVE_LOSSES", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_CONSECUTIVE_LOSSES)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_DRAWDOWN_PCT", str(PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_DRAWDOWN_PCT)))
    PAPER_UNLOCK_SHADOW_DRY_RUN_REQUIRE_EXPERIMENT_READY: bool = os.getenv("PAPER_UNLOCK_SHADOW_DRY_RUN_REQUIRE_EXPERIMENT_READY", "1") == "1"

    # Prompt 29.4.4f — shadow dry-run sample expansion / rate-limit calibration.
    # Diagnostic-only: compares bounded rate-limit profiles and an all-shadow ceiling.
    # It never enables paper orders, testnet or live.
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED", "1") == "1"
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_HISTORICAL_ENABLED", str(int(PAPER_UNLOCK_SHADOW_DRY_RUN_HISTORICAL_ENABLED))) == "1"
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REPORT_PATH", os.path.join("data", "paper_unlock_shadow_rate_calibration_report.json"))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_NAME: str = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_RATE_CALIBRATION")
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_ROWS_PER_ASSET", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_EVAL_STRIDE", str(PAPER_UNLOCK_SHADOW_DRY_RUN_EVAL_STRIDE)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_STRUCTURE_WINDOW_ROWS", str(PAPER_UNLOCK_SHADOW_DRY_RUN_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_VARIANT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_VARIANT_CANDIDATES", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_VARIANT_CANDIDATES)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_ENTRIES", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_ENTRIES)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_EXPECTANCY_R", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_EXPECTANCY_R)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_LOSS_RATE_PCT", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_LOSS_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_TIME_EXIT_RATE_PCT", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MIN", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MAX", str(PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_RISK_PER_TRADE_PCT", str(PAPER_UNLOCK_SHADOW_DRY_RUN_RISK_PER_TRADE_PCT)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_CONSECUTIVE_LOSSES", str(PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_CONSECUTIVE_LOSSES)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_DRAWDOWN_PCT", str(PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_DRAWDOWN_PCT)))
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_EXPERIMENT_READY: bool = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_EXPERIMENT_READY", str(int(PAPER_UNLOCK_SHADOW_DRY_RUN_REQUIRE_EXPERIMENT_READY))) == "1"
    PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_RATE_LIMITED_PROFILE: bool = os.getenv("PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_RATE_LIMITED_PROFILE", "1") == "1"

    # Prompt 29.4.4g — bounded cadence expansion / rolling shadow collection.
    # Diagnostic-only: tests additional bounded cadence profiles after 29.4.4f.
    # It never enables paper orders, testnet or live.
    PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED: bool = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED", "1") == "1"
    PAPER_UNLOCK_BOUNDED_CADENCE_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_HISTORICAL_ENABLED", str(int(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_HISTORICAL_ENABLED))) == "1"
    PAPER_UNLOCK_BOUNDED_CADENCE_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_REPORT_PATH", os.path.join("data", "paper_unlock_bounded_cadence_report.json"))
    PAPER_UNLOCK_BOUNDED_CADENCE_NAME: str = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_BOUNDED_CADENCE_COLLECTION")
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ROWS_PER_ASSET", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_BOUNDED_CADENCE_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_EVAL_STRIDE", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_EVAL_STRIDE)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_BOUNDED_CADENCE_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_STRUCTURE_WINDOW_ROWS", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MIN_VARIANT_CANDIDATES: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MIN_VARIANT_CANDIDATES", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_VARIANT_CANDIDATES)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MIN_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MIN_ENTRIES", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_ENTRIES)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MIN_EXPECTANCY_R", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_EXPECTANCY_R)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_LOSS_RATE_PCT", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_LOSS_RATE_PCT)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_TIME_EXIT_RATE_PCT", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MIN", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MAX", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_BOUNDED_CADENCE_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_RISK_PER_TRADE_PCT", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_RISK_PER_TRADE_PCT)))
    PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_CONSECUTIVE_LOSSES", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_CONSECUTIVE_LOSSES)))
    PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_DRAWDOWN_PCT", str(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_DRAWDOWN_PCT)))
    PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_EXPERIMENT_READY: bool = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_EXPERIMENT_READY", str(int(PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_EXPERIMENT_READY))) == "1"
    PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_RATE_CALIBRATION: bool = os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_RATE_CALIBRATION", "1") == "1"
    PAPER_UNLOCK_BOUNDED_CADENCE_MIN_POSITIVE_WINDOW_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MIN_POSITIVE_WINDOW_RATE_PCT", "66.67"))
    PAPER_UNLOCK_BOUNDED_CADENCE_MIN_HOLDOUT_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MIN_HOLDOUT_ENTRIES", "5"))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ASSET_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ASSET_CONCENTRATION_PCT", "75.0"))
    PAPER_UNLOCK_BOUNDED_CADENCE_MAX_SIDE_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_BOUNDED_CADENCE_MAX_SIDE_CONCENTRATION_PCT", "85.0"))


    # Prompt 29.4.4h — shadow sample stability review.
    # Diagnostic-only: reviews the bounded cadence sample from 29.4.4g before any activation draft.
    # It never enables paper orders, testnet or live.
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED", "1") == "1"
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_HISTORICAL_ENABLED: bool = os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_HISTORICAL_ENABLED", str(int(PAPER_UNLOCK_BOUNDED_CADENCE_HISTORICAL_ENABLED))) == "1"
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_REPORT_PATH", os.path.join("data", "paper_unlock_shadow_stability_review_report.json"))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_NAME: str = os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_SAMPLE_STABILITY_REVIEW")
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ROWS_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ROWS_PER_ASSET", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ROWS_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_EVAL_STRIDE: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_EVAL_STRIDE", str(PAPER_UNLOCK_BOUNDED_CADENCE_EVAL_STRIDE)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_STRUCTURE_CANDIDATES_PER_ASSET: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_STRUCTURE_CANDIDATES_PER_ASSET)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_STRUCTURE_WINDOW_ROWS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_STRUCTURE_WINDOW_ROWS", str(PAPER_UNLOCK_BOUNDED_CADENCE_STRUCTURE_WINDOW_ROWS)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_ENTRIES", str(PAPER_UNLOCK_BOUNDED_CADENCE_MIN_ENTRIES)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_EXPECTANCY_R: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_EXPECTANCY_R", str(PAPER_UNLOCK_BOUNDED_CADENCE_MIN_EXPECTANCY_R)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_LOSS_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_LOSS_RATE_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_LOSS_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_TIME_EXIT_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_TIME_EXIT_RATE_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_TIME_EXIT_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_CONSECUTIVE_LOSSES", str(PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_CONSECUTIVE_LOSSES)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_DRAWDOWN_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_DRAWDOWN_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MIN: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MIN", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MIN)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MAX: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MAX", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MAX)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_RISK_PER_TRADE_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_RISK_PER_TRADE_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_REQUIRE_BOUNDED_CADENCE: bool = os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_REQUIRE_BOUNDED_CADENCE", "1") == "1"
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_POSITIVE_WINDOW_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_POSITIVE_WINDOW_RATE_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_MIN_POSITIVE_WINDOW_RATE_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_HOLDOUT_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_HOLDOUT_ENTRIES", str(PAPER_UNLOCK_BOUNDED_CADENCE_MIN_HOLDOUT_ENTRIES)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ASSET_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ASSET_CONCENTRATION_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ASSET_CONCENTRATION_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SIDE_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SIDE_CONCENTRATION_PCT", str(PAPER_UNLOCK_BOUNDED_CADENCE_MAX_SIDE_CONCENTRATION_PCT)))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_ASSETS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_ASSETS", "2"))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_SIDES: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_SIDES", "2"))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_DAYS: int = int(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_DAYS", "3"))
    PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SINGLE_DAY_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SINGLE_DAY_CONCENTRATION_PCT", "45.0"))

    # Prompt 29.4.4i - guarded paper-only activation draft / safety interlock design
    PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED: bool = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED", "1") == "1"
    PAPER_UNLOCK_ACTIVATION_DRAFT_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REPORT_PATH", os.path.join("data", "paper_unlock_activation_draft_report.json"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_NAME: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT")
    PAPER_UNLOCK_ACTIVATION_DRAFT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_ACTIVATION_DRAFT_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_STABILITY_DECISION: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_STABILITY_DECISION", "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC")
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOURS_BETWEEN_ENTRIES: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOURS_BETWEEN_ENTRIES", "0.0"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_DRAWDOWN_PCT", "1.0"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_POSITIVE_WINDOW_RATE_PCT: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_POSITIVE_WINDOW_RATE_PCT", "66.67"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOLDOUT_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOLDOUT_ENTRIES", "5"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_ASSET_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_ASSET_CONCENTRATION_PCT", "75.0"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_SIDE_CONCENTRATION_PCT: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_SIDE_CONCENTRATION_PCT", "85.0"))
    PAPER_UNLOCK_ACTIVATION_DRAFT_CONFIRMATION_ONLY: bool = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_CONFIRMATION_ONLY", "1") == "1"
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_MANUAL_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_MANUAL_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_STABILITY_REVIEW: bool = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_STABILITY_REVIEW", "1") == "1"
    PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_REPORT_AGE_HOURS: float = float(os.getenv("PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_REPORT_AGE_HOURS", "0.0"))

    # Prompt 29.4.4j - guarded paper-only experiment switch implementation draft (diagnostic-only)
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REPORT_PATH", os.path.join("data", "paper_unlock_experiment_switch_draft_report.json"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ACTIVATION_DRAFT_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ACTIVATION_DRAFT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_ACTIVATION_DECISION: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_ACTIVATION_DECISION", "GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_SEPARATE_PATCH: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_SEPARATE_PATCH", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_CONFIRMATION_ONLY: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_CONFIRMATION_ONLY", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_DRAWDOWN_PCT", "1.0"))
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPECTED_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPECTED_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY")
    PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_REPORT_AGE_HOURS: float = float(os.getenv("PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_REPORT_AGE_HOURS", "0.0"))


    # Prompt 29.4.4k - manual paper-only switch dry-run / fail-closed preflight (diagnostic-only)
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED: bool = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED", "1") == "1"
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REPORT_PATH", os.path.join("data", "paper_unlock_manual_switch_preflight_report.json"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_SWITCH_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_SWITCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SWITCH_DECISION: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SWITCH_DECISION", "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPECTED_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPECTED_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUESTED_MODE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_TESTNET_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_LIVE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXCHANGE_BROKER_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER")
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED: bool = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED", "1") == "1"
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_SEPARATE_PATCH: bool = os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_SEPARATE_PATCH", "1") == "1"
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT", "1.0"))


    # Prompt 29.4.4l - explicit manual paper-only activation patch draft (diagnostic-only)
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ENABLED: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ENABLED", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REPORT_PATH", os.path.join("data", "paper_unlock_manual_activation_patch_report.json"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PREFLIGHT_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PREFLIGHT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_SWITCH_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_SWITCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_PREFLIGHT_DECISION: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_PREFLIGHT_DECISION", "MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MANUAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MANUAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPECTED_MANUAL_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPECTED_MANUAL_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PATCH_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_PATCH_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_CONFIRM_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPECTED_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXPECTED_CONFIRM_VALUE", "ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUESTED_MODE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_TESTNET_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_LIVE_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXCHANGE_BROKER_ENV: str = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER")
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_EXCHANGE_BROKER_BLOCKED: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_EXCHANGE_BROKER_BLOCKED", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_EXPLICIT_PATCH: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_EXPLICIT_PATCH", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_CONFIRM: bool = os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_REQUIRE_CONFIRM", "1") == "1"
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ABORT_MAX_DRAWDOWN_PCT", "1.0"))

    # Prompt 29.4.4m - final manual paper-only enable preflight / activation candidate
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REPORT_PATH", os.path.join("data", "paper_unlock_final_enable_preflight_report.json"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PREFLIGHT_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PREFLIGHT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_SWITCH_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_SWITCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_ACTIVATION_DECISION: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_ACTIVATION_DECISION", "EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT_READY_DIAGNOSTIC")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_MANUAL_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_MANUAL_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_CONFIRM_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_ACTIVATION_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_ACTIVATION_CONFIRM_VALUE", "ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_ENABLE_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_CONFIRM_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_FINAL_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_FINAL_CONFIRM_VALUE", "ENABLE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_CANDIDATE")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUESTED_MODE_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_TESTNET_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_LIVE_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXCHANGE_BROKER_ENV: str = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER")
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_PATCH: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_PATCH", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_CONFIRM: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_CONFIRM", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_ENABLE_PATCH: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_ENABLE_PATCH", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_CONFIRM: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_CONFIRM", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ALLOW_CANDIDATE: bool = os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ALLOW_CANDIDATE", "1") == "1"
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT", "1.0"))

    # Prompt 29.4.4n - guarded paper-only experiment enable / operator-controlled paper orders
    PAPER_UNLOCK_GUARDED_ENABLE_ENABLED: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ENABLED", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REPORT_PATH: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REPORT_PATH", os.path.join("data", "paper_unlock_guarded_enable_report.json"))
    PAPER_UNLOCK_GUARDED_ENABLE_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE")
    PAPER_UNLOCK_GUARDED_ENABLE_FINAL_PREFLIGHT_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_FINAL_PREFLIGHT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT")
    PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT")
    PAPER_UNLOCK_GUARDED_ENABLE_SWITCH_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_SWITCH_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT")
    PAPER_UNLOCK_GUARDED_ENABLE_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_GUARDED_ENABLE_EXPERIMENT_NAME: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXPERIMENT_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN")
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_FINAL_PREFLIGHT_DECISION: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_FINAL_PREFLIGHT_DECISION", "FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC")
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_SELECTED_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_SELECTED_ENTRIES", "20"))
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_CADENCE_VARIANT: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h")
    PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE")
    PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM")
    PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_MANUAL_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_MANUAL_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY")
    PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH")
    PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_CONFIRM_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM")
    PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_ACTIVATION_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_ACTIVATION_CONFIRM_VALUE", "ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT")
    PAPER_UNLOCK_GUARDED_ENABLE_FINAL_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_FINAL_ENABLE_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH")
    PAPER_UNLOCK_GUARDED_ENABLE_FINAL_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_FINAL_CONFIRM_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM")
    PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_FINAL_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_FINAL_CONFIRM_VALUE", "ENABLE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_CANDIDATE")
    PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_ENABLE_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_ENABLE_ENV", "PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS")
    PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_CONFIRM_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_CONFIRM_ENV", "PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS")
    PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_OPERATOR_CONFIRM_VALUE: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_OPERATOR_CONFIRM_VALUE", "OPERATOR_CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ORDERS")
    PAPER_UNLOCK_GUARDED_ENABLE_REQUESTED_MODE_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE")
    PAPER_UNLOCK_GUARDED_ENABLE_TESTNET_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET")
    PAPER_UNLOCK_GUARDED_ENABLE_LIVE_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE")
    PAPER_UNLOCK_GUARDED_ENABLE_EXCHANGE_BROKER_ENV: str = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER")
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_PAPER_MODE: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_PAPER_MODE", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_EXCHANGE_BROKER_BLOCKED: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_EXCHANGE_BROKER_BLOCKED", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_TWO_STEP: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_TWO_STEP", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_PATCH: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_PATCH", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_CONFIRM: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_CONFIRM", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_ENABLE_PATCH: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_ENABLE_PATCH", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_CONFIRM: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_CONFIRM", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_ENABLE: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_ENABLE", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_CONFIRM: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_CONFIRM", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_ALLOW_PAPER_ORDERS: bool = os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ALLOW_PAPER_ORDERS", "1") == "1"
    PAPER_UNLOCK_GUARDED_ENABLE_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_GUARDED_ENABLE_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_GUARDED_ENABLE_MAX_DAILY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_MAX_DAILY_ENTRIES", "6"))
    PAPER_UNLOCK_GUARDED_ENABLE_MAX_WEEKLY_ENTRIES: int = int(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_MAX_WEEKLY_ENTRIES", "30"))
    PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_CONSECUTIVE_LOSSES", "3"))
    PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_DRAWDOWN_PCT: float = float(os.getenv("PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_DRAWDOWN_PCT", "1.0"))

    # Prompt 29.4.4o - runtime paper-order audit / first controlled paper-cycle monitoring
    PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REPORT_NAME", "paper_unlock_runtime_audit_report.json")
    PAPER_UNLOCK_RUNTIME_AUDIT_GUARDED_ENABLE_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_GUARDED_ENABLE_REPORT_NAME", "paper_unlock_guarded_enable_report.json")
    PAPER_UNLOCK_RUNTIME_AUDIT_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_RUNTIME_AUDIT_STATUS_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_STATUS_NAME", "paper_status.json")
    PAPER_UNLOCK_RUNTIME_AUDIT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_RUNTIME_AUDIT_ENABLE_NAME: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_ENABLE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE")
    PAPER_UNLOCK_RUNTIME_AUDIT_LEGACY_PROFILE: str = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_LEGACY_PROFILE", "BTC_ONLY_40_Q60")
    PAPER_UNLOCK_RUNTIME_AUDIT_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_MAX_EVENT_LINES", "5000"))
    PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MIN: float = float(os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MIN", "65.0"))
    PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MAX: float = float(os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MAX", "79.999"))
    PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_PAPER_ORDERS_ENABLED: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_PAPER_ORDERS_ENABLED", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_EXPERIMENT_ALLOWED: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_EXPERIMENT_ALLOWED", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_MANUAL_ACTIVATION: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_MANUAL_ACTIVATION", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_OPERATOR_CONTROLLED_DECISION: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_OPERATOR_CONTROLLED_DECISION", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_CONFIRMATION_ONLY: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_CONFIRMATION_ONLY", "1") == "1"
    PAPER_UNLOCK_RUNTIME_AUDIT_EMIT_EVENTS: bool = os.getenv("PAPER_UNLOCK_RUNTIME_AUDIT_EMIT_EVENTS", "1") == "1"

    # Prompt 29.4.4p - guarded paper-only routing bridge / accepted-signal order simulation
    PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED: bool = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED", "1") == "1"
    PAPER_UNLOCK_ROUTING_BRIDGE_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_REPORT_NAME", "paper_unlock_routing_bridge_report.json")
    PAPER_UNLOCK_ROUTING_BRIDGE_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_ROUTING_BRIDGE_STATUS_NAME: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_STATUS_NAME", "paper_status.json")
    PAPER_UNLOCK_ROUTING_BRIDGE_RUNTIME_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_RUNTIME_EVENT_TYPE", "GUARDED_PAPER_RUNTIME_AUDIT")
    PAPER_UNLOCK_ROUTING_BRIDGE_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_EVENT_TYPE", "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT")
    PAPER_UNLOCK_ROUTING_BRIDGE_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_ROUTING_BRIDGE_ENABLE_NAME: str = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_ENABLE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE")
    PAPER_UNLOCK_ROUTING_BRIDGE_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_MAX_EVENT_LINES", "5000"))
    PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MIN: float = float(os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MIN", "65.0"))
    PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MAX: float = float(os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MAX", "79.999"))
    PAPER_UNLOCK_ROUTING_BRIDGE_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_ROUTING_BRIDGE_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_ROUTING_BRIDGE_EMIT_EVENTS: bool = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_EMIT_EVENTS", "1") == "1"
    PAPER_UNLOCK_ROUTING_BRIDGE_SIMULATION_ONLY: bool = os.getenv("PAPER_UNLOCK_ROUTING_BRIDGE_SIMULATION_ONLY", "1") == "1"

    # Prompt 29.4.4q - first guarded paper-order candidate audit
    PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED: bool = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED", "1") == "1"
    PAPER_UNLOCK_CANDIDATE_AUDIT_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_REPORT_NAME", "paper_unlock_candidate_audit_report.json")
    PAPER_UNLOCK_CANDIDATE_AUDIT_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_CANDIDATE_AUDIT_STATUS_NAME: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_STATUS_NAME", "paper_status.json")
    PAPER_UNLOCK_CANDIDATE_AUDIT_BRIDGE_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_BRIDGE_EVENT_TYPE", "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT")
    PAPER_UNLOCK_CANDIDATE_AUDIT_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_EVENT_TYPE", "GUARDED_PAPER_ORDER_CANDIDATE_AUDIT")
    PAPER_UNLOCK_CANDIDATE_AUDIT_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLE_NAME: str = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE")
    PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_EVENT_LINES", "5000"))
    PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_CANDIDATE_AUDIT_RISK_PER_TRADE_PCT: float = float(os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_RISK_PER_TRADE_PCT", "0.0025"))
    PAPER_UNLOCK_CANDIDATE_AUDIT_RR: float = float(os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_RR", "2.0"))
    PAPER_UNLOCK_CANDIDATE_AUDIT_EMIT_EVENTS: bool = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_EMIT_EVENTS", "1") == "1"
    PAPER_UNLOCK_CANDIDATE_AUDIT_ONLY: bool = os.getenv("PAPER_UNLOCK_CANDIDATE_AUDIT_ONLY", "1") == "1"


    # Prompt 29.4.4r - paper order submission dry-run / simulated broker handoff
    PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED: bool = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED", "1") == "1"
    PAPER_UNLOCK_HANDOFF_DRY_RUN_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_REPORT_NAME", "paper_unlock_handoff_dry_run_report.json")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_STATUS_NAME: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_STATUS_NAME", "paper_status.json")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_CANDIDATE_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_CANDIDATE_EVENT_TYPE", "GUARDED_PAPER_ORDER_CANDIDATE_AUDIT")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENT_TYPE", "PAPER_ORDER_HANDOFF_DRY_RUN")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_PROFILE_NAME: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_PROFILE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLE_NAME: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLE_NAME", "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE")
    PAPER_UNLOCK_HANDOFF_DRY_RUN_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_MAX_EVENT_LINES", "5000"))
    PAPER_UNLOCK_HANDOFF_DRY_RUN_EMIT_EVENTS: bool = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_EMIT_EVENTS", "1") == "1"
    PAPER_UNLOCK_HANDOFF_DRY_RUN_ONLY: bool = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_ONLY", "1") == "1"
    PAPER_UNLOCK_HANDOFF_DRY_RUN_PAPER_BROKER_ADAPTER: str = os.getenv("PAPER_UNLOCK_HANDOFF_DRY_RUN_PAPER_BROKER_ADAPTER", "PaperBrokerAdapter")

    # Prompt 29.4.4r-1 - legacy paper order leakage audit + fail-closed guard
    PAPER_ORDER_LEAKAGE_GUARD_ENABLED: bool = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_ENABLED", "1") == "1"

    # Prompt 29.4.4s-4 — diagnostic archetype pruning / runtime gate.
    # Default is audit-only. Blocking requires explicit operator enable.
    EDGE_STRATEGY_PRUNING_ENABLED: bool = os.getenv("EDGE_STRATEGY_PRUNING_ENABLED", "0") == "1"
    EDGE_STRATEGY_PRUNING_AUDIT_ENABLED: bool = os.getenv("EDGE_STRATEGY_PRUNING_AUDIT_ENABLED", "1") == "1"
    EDGE_STRATEGY_PRUNING_FAIL_CLOSED: bool = os.getenv("EDGE_STRATEGY_PRUNING_FAIL_CLOSED", "1") == "1"
    EDGE_STRATEGY_BLOCKED_ARCHETYPES: str = os.getenv("EDGE_STRATEGY_BLOCKED_ARCHETYPES", "RANGING_MEAN_REVERSION")
    EDGE_STRATEGY_WATCHLIST_ARCHETYPES: str = os.getenv("EDGE_STRATEGY_WATCHLIST_ARCHETYPES", "LIQUIDITY_SWEEP_REVERSAL")
    EDGE_STRATEGY_RUNTIME_PRUNING_REPORT: str = os.getenv("EDGE_STRATEGY_RUNTIME_PRUNING_REPORT", "edge_strategy_runtime_pruning_report.json")
    PAPER_ORDER_LEAKAGE_GUARD_FAIL_CLOSED: bool = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_FAIL_CLOSED", "1") == "1"
    # Prompt 29.4.4s allows only metadata-marked guarded supervised paper orders.
    # Legacy ScoreOnly/Meta_OK events still lack guarded_supervised_execution and remain blocked.
    PAPER_ORDER_LEAKAGE_GUARD_ALLOW_SUPERVISED: bool = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_ALLOW_SUPERVISED", "1") == "1"
    PAPER_ORDER_LEAKAGE_GUARD_REPORT_NAME: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_REPORT_NAME", "paper_order_leakage_guard_report.json")
    PAPER_ORDER_LEAKAGE_GUARD_EVENTS_NAME: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_EVENTS_NAME", "paper_events.jsonl")
    PAPER_ORDER_LEAKAGE_GUARD_STATUS_NAME: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_STATUS_NAME", "paper_status.json")
    PAPER_ORDER_LEAKAGE_GUARD_MAX_EVENT_LINES: int = int(os.getenv("PAPER_ORDER_LEAKAGE_GUARD_MAX_EVENT_LINES", "50000"))
    PAPER_ORDER_LEAKAGE_GUARD_EVENT_TYPE: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_EVENT_TYPE", "LEGACY_PAPER_ORDER_LEAKAGE_AUDIT")
    PAPER_ORDER_LEAKAGE_GUARD_BLOCKED_EVENT_TYPE: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_BLOCKED_EVENT_TYPE", "LEGACY_PAPER_ORDER_BLOCKED")
    PAPER_ORDER_LEAKAGE_GUARD_ALLOWED_SOURCE: str = os.getenv("PAPER_ORDER_LEAKAGE_GUARD_ALLOWED_SOURCE", "NONE")

    # Prompt 29.4.4s - first real paper-only order execution, supervised
    PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED: bool = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED", "1") == "1"
    PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE: bool = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE", "0") == "1"
    PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM", "")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM_PHRASE: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM_PHRASE", "I_UNDERSTAND_PAPER_ONLY")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_REPORT_NAME", "paper_unlock_supervised_execution_report.json")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_STATUS_NAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_STATUS_NAME", "paper_status.json")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENT_TYPE", "PAPER_SUPERVISED_ORDER_EXECUTION")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_HANDOFF_EVENT_TYPE: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_HANDOFF_EVENT_TYPE", "PAPER_ORDER_HANDOFF_DRY_RUN")
    PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_EVENT_LINES", "50000"))
    PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_POSITIONS: int = int(os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_POSITIONS", "1"))
    PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_ORDERS_PER_CYCLE: int = int(os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_ORDERS_PER_CYCLE", "1"))
    PAPER_UNLOCK_SUPERVISED_EXECUTION_PAPER_BROKER_ADAPTER: str = os.getenv("PAPER_UNLOCK_SUPERVISED_EXECUTION_PAPER_BROKER_ADAPTER", "PaperBrokerAdapter")

    # Prompt 29.4.4s-OBS - supervised inactive observation / candidate exposure monitor
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_REPORT_NAME", "paper_unlock_supervised_inactive_observation_report.json")
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_EVENT_LINES", "100000"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_DURATION_HOURS: float = float(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_DURATION_HOURS", "4.0"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_INTERVAL_SECONDS: float = float(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_INTERVAL_SECONDS", "300.0"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_CYCLES: int = int(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_CYCLES", "0"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_TIMEFRAME: str = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_TIMEFRAME", "5m")
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COST_MODEL: str = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COST_MODEL", "conservative")
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_BALANCE: float = float(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_BALANCE", "1000"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_POLL_SECONDS: float = float(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_POLL_SECONDS", "60.0"))
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_PAPER_UNLOCK: bool = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_PAPER_UNLOCK", "1") == "1"
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_LOG_DIR: str = os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_LOG_DIR", "paper_unlock_supervised_inactive_observation_logs")
    PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COMMAND_TIMEOUT_SECONDS: float = float(os.getenv("PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COMMAND_TIMEOUT_SECONDS", "900.0"))

    # Prompt 29.4.4r-2 - legacy paper position quarantine / clean-state preflight
    PAPER_LEGACY_QUARANTINE_REPORT_NAME: str = os.getenv("PAPER_LEGACY_QUARANTINE_REPORT_NAME", "paper_legacy_position_quarantine_report.json")
    PAPER_LEGACY_QUARANTINE_BACKUP_DIR: str = os.getenv("PAPER_LEGACY_QUARANTINE_BACKUP_DIR", "paper_legacy_quarantine_backups")
    PAPER_LEGACY_QUARANTINE_EVENTS_NAME: str = os.getenv("PAPER_LEGACY_QUARANTINE_EVENTS_NAME", "paper_events.jsonl")
    PAPER_LEGACY_QUARANTINE_STATE_NAME: str = os.getenv("PAPER_LEGACY_QUARANTINE_STATE_NAME", "paper_state.json")
    PAPER_LEGACY_QUARANTINE_STATUS_NAME: str = os.getenv("PAPER_LEGACY_QUARANTINE_STATUS_NAME", "paper_status.json")
    PAPER_LEGACY_QUARANTINE_MONITOR_NAME: str = os.getenv("PAPER_LEGACY_QUARANTINE_MONITOR_NAME", "paper_position_monitor.json")

    # Prompt 29.4.4q-OBS — 4h audit-only observation run controls.
    PAPER_UNLOCK_OBSERVATION_REPORT_NAME: str = os.getenv("PAPER_UNLOCK_OBSERVATION_REPORT_NAME", "paper_unlock_4h_observation_report.json")
    PAPER_UNLOCK_OBSERVATION_EVENTS_NAME: str = os.getenv("PAPER_UNLOCK_OBSERVATION_EVENTS_NAME", "paper_events.jsonl")
    PAPER_UNLOCK_OBSERVATION_MAX_EVENT_LINES: int = int(os.getenv("PAPER_UNLOCK_OBSERVATION_MAX_EVENT_LINES", "50000"))
    PAPER_UNLOCK_OBSERVATION_DURATION_HOURS: float = float(os.getenv("PAPER_UNLOCK_OBSERVATION_DURATION_HOURS", "4.0"))
    PAPER_UNLOCK_OBSERVATION_INTERVAL_SECONDS: float = float(os.getenv("PAPER_UNLOCK_OBSERVATION_INTERVAL_SECONDS", "300.0"))
    PAPER_UNLOCK_OBSERVATION_MAX_CYCLES: int = int(os.getenv("PAPER_UNLOCK_OBSERVATION_MAX_CYCLES", "0"))
    PAPER_UNLOCK_OBSERVATION_TIMEFRAME: str = os.getenv("PAPER_UNLOCK_OBSERVATION_TIMEFRAME", "5m")
    PAPER_UNLOCK_OBSERVATION_COST_MODEL: str = os.getenv("PAPER_UNLOCK_OBSERVATION_COST_MODEL", "conservative")
    PAPER_UNLOCK_OBSERVATION_BALANCE: float = float(os.getenv("PAPER_UNLOCK_OBSERVATION_BALANCE", "1000"))
    PAPER_UNLOCK_OBSERVATION_POLL_SECONDS: float = float(os.getenv("PAPER_UNLOCK_OBSERVATION_POLL_SECONDS", "60.0"))
    PAPER_UNLOCK_OBSERVATION_PAPER_UNLOCK: bool = os.getenv("PAPER_UNLOCK_OBSERVATION_PAPER_UNLOCK", "1") == "1"
    PAPER_UNLOCK_OBSERVATION_LOG_DIR: str = os.getenv("PAPER_UNLOCK_OBSERVATION_LOG_DIR", "paper_unlock_observation_logs")
    PAPER_UNLOCK_OBSERVATION_COMMAND_TIMEOUT_SECONDS: float = float(os.getenv("PAPER_UNLOCK_OBSERVATION_COMMAND_TIMEOUT_SECONDS", "900.0"))

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