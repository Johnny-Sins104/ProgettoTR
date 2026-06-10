from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_bot.strategy_runtime.strategy_config_store import load_runtime_config, read_position_state
from trading_bot.strategy_runtime.strategy_signal_schema import SUPPORTED_STRATEGIES


DISPLAY_NAMES = {
    "ema_vwap": "EMA + RSI + VWAP",
    "bb": "Bollinger Bands",
    "macd": "MACD Cross",
    "ichimoku": "Ichimoku",
    "auto": "Auto (read-only)",
}


def dashboard_state(data_dir: Path) -> dict[str, Any]:
    config = load_runtime_config(data_dir)
    position = read_position_state(data_dir)
    active = str(config.get("active_strategy", "bb"))
    return {
        "active_strategy": active,
        "active_strategy_label": DISPLAY_NAMES.get(active, active),
        "supported_strategies": list(SUPPORTED_STRATEGIES),
        "strategy_labels": DISPLAY_NAMES,
        "mode": config.get("mode", "paper"),
        "can_trade": False,
        "reason": config.get("reason", "selector_read_only_stage"),
        "position_state": position,
        "open_positions": int(position.get("open_positions", 0) or 0) if position.get("readable") else None,
        "strategy_switch_blocked": bool(position.get("readable") and int(position.get("open_positions", 0) or 0) > 0),
        "strategy_switch_block_reason": "open_position_strategy_switch_blocked"
        if position.get("readable") and int(position.get("open_positions", 0) or 0) > 0
        else "",
        "calibration_status": "DIAGNOSTIC_ONLY",
        "paper_trading_activation_allowed": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
    }
