from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_bot.dashboard.strategy_dashboard_state import dashboard_state
from trading_bot.strategy_runtime.selected_strategy_shadow_diagnostics import build_selected_strategy_shadow_stats
from trading_bot.strategy_runtime.selected_strategy_shadow_journal import (
    append_shadow_event,
    build_shadow_journal_event,
    latest_shadow_event,
    read_shadow_events,
)
from trading_bot.strategy_runtime.strategy_calibration_registry import calibrate_strategy
from trading_bot.strategy_runtime.strategy_config_store import select_strategy
from trading_bot.strategy_runtime.strategy_shadow_report import build_and_write_shadow_report
from trading_bot.strategy_runtime.strategy_signal_schema import SUPPORTED_STRATEGIES


def get_strategy_status(data_dir: Path | str = "data") -> dict[str, Any]:
    root = Path(data_dir)
    state = dashboard_state(root)
    shadow = build_and_write_shadow_report(data_dir=root)
    signal = shadow.get("signal", {})
    journal_event = build_shadow_journal_event(
        execution_report={
            "active_strategy": shadow.get("active_strategy"),
            "active_strategy_label": shadow.get("active_strategy_label"),
            "signal": signal,
        },
        asset=str(shadow.get("asset") or "XRP/USDT"),
        timeframe=str(shadow.get("timeframe") or "5m"),
    )
    journal_append = append_shadow_event(root, journal_event)
    latest_event = latest_shadow_event(root)
    stats = build_selected_strategy_shadow_stats(root, strategy=str(state.get("active_strategy") or ""))
    return {
        "status": "OK",
        **state,
        "shadow_signal_available": shadow.get("shadow_signal_available", False),
        "last_shadow_signal": signal,
        "signal": signal.get("signal", "WAIT"),
        "score": signal.get("score", 0),
        "conditions": signal.get("conditions", []),
        "block_reasons": signal.get("block_reasons", []),
        "would_trade": False,
        "shadow_only": True,
        "can_trade": False,
        "shadow_journal_available": (root / "selected_strategy_shadow_signal_journal.jsonl").exists(),
        "shadow_events_recorded": len(read_shadow_events(root)),
        "shadow_journal_append_status": journal_append.get("status", "UNKNOWN"),
        "latest_shadow_event": latest_event,
        "selected_strategy_shadow_stats": stats,
        "outcome_tracking_status": "SCAFFOLD_ONLY",
        "outcome_tracking_scaffold": latest_event.get("outcome_tracking", {}) if latest_event else {},
    }


def post_strategy_select(payload: dict[str, Any], data_dir: Path | str = "data") -> dict[str, Any]:
    strategy = str(payload.get("strategy", ""))
    return select_strategy(Path(data_dir), strategy, updated_by="dashboard")


def post_strategy_calibrate(payload: dict[str, Any], data_dir: Path | str = "data") -> dict[str, Any]:
    strategy = str(payload.get("strategy") or dashboard_state(Path(data_dir)).get("active_strategy") or "bb")
    asset = str(payload.get("asset") or "BTC/USDT")
    timeframe = str(payload.get("timeframe") or "5m")
    regime = str(payload.get("regime") or "unknown")
    if strategy not in SUPPORTED_STRATEGIES:
        return {"status": "REJECTED", "reason": "unsupported_strategy", "supported_strategies": list(SUPPORTED_STRATEGIES)}
    report = calibrate_strategy(Path(data_dir), strategy=strategy, asset=asset, timeframe=timeframe, regime=regime)
    return {"status": "OK", "calibration": report}
