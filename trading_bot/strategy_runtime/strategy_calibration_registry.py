from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_bot.strategy_runtime.strategy_config_store import utc_now
from trading_bot.strategy_runtime.strategy_signal_schema import validate_strategy_id


DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "ema_vwap": {
        "fast_ema": 20,
        "slow_ema": 50,
        "rsi_period": 14,
        "min_score": 70,
        "sl_atr_multiple": 1.2,
        "tp_multiple": 1.8,
    },
    "bb": {
        "bb_period": 20,
        "bb_dev": 2.0,
        "max_band_width_pct": 3.0,
        "min_score": 70,
        "sl_atr_multiple": 1.2,
        "tp_multiple": 1.8,
    },
    "macd": {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "min_score": 65,
        "sl_atr_multiple": 1.2,
        "tp_multiple": 1.8,
    },
    "ichimoku": {
        "tenkan": 9,
        "kijun": 26,
        "senkou_b": 52,
        "min_score": 75,
        "sl_atr_multiple": 1.4,
        "tp_multiple": 2.0,
    },
    "auto": {
        "enabled": False,
        "reason": "auto_strategy_disabled_in_preflight",
    },
}


def profile_path(data_dir: Path, asset: str, timeframe: str, strategy: str) -> Path:
    safe_asset = str(asset or "UNKNOWN").upper().replace("/", "").replace(":", "")
    safe_timeframe = str(timeframe or "UNKNOWN").lower().replace("/", "_")
    safe_strategy = validate_strategy_id(strategy)
    return data_dir / "strategy_profiles" / f"{safe_asset}_{safe_timeframe}_{safe_strategy}.json"


def calibrate_strategy(
    data_dir: Path,
    *,
    strategy: str,
    asset: str,
    timeframe: str,
    regime: str = "unknown",
) -> dict[str, Any]:
    normalized = validate_strategy_id(strategy)
    report = {
        "strategy": normalized,
        "asset": asset,
        "timeframe": timeframe,
        "regime": regime,
        "status": "DIAGNOSTIC_ONLY",
        "best_params": DEFAULT_PARAMS[normalized],
        "can_trade": False,
        "reason": "calibration_scaffold_only",
        "paper_trading_activation_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
        "would_submit": False,
        "would_close": False,
        "generated_at": utc_now(),
    }
    path = profile_path(data_dir, asset, timeframe, normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return {**report, "profile_path": str(path)}
