from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.strategy_runtime.strategy_config_store import utc_now
from trading_bot.strategy_runtime.strategy_signal_executor import execute_shadow_signal


def shadow_report_path(data_dir: Path) -> Path:
    return data_dir / "strategy_shadow_signal_report.json"


def build_shadow_report(
    *,
    data_dir: Path,
    asset: str = "XRP/USDT",
    timeframe: str = "5m",
    max_rows: int = 500,
    df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    execution = execute_shadow_signal(
        data_dir,
        asset=asset,
        timeframe=timeframe,
        max_rows=max_rows,
        df=df,
    )
    signal = execution["signal"]
    ready = (
        signal.get("shadow_only") is True
        and signal.get("would_trade") is False
        and signal.get("can_trade") is False
        and execution.get("single_strategy_execution_confirmed") is True
    )
    return {
        "status": "PASS" if ready else "FAIL",
        "decision": "STRATEGY_SELECTOR_SHADOW_SIGNAL_EXECUTION_READY"
        if ready
        else "STRATEGY_SELECTOR_SHADOW_SIGNAL_EXECUTION_BLOCKED",
        "generated_at": utc_now(),
        "asset": asset,
        "timeframe": timeframe,
        "active_strategy": execution.get("active_strategy", ""),
        "active_strategy_label": execution.get("active_strategy_label", ""),
        "shadow_signal_available": True,
        "shadow_only": True,
        "single_strategy_execution_confirmed": execution.get("single_strategy_execution_confirmed") is True,
        "auto_strategy_execution_allowed": False,
        "signal": signal,
        "score": signal.get("score", 0),
        "conditions": signal.get("conditions", []),
        "block_reasons": signal.get("block_reasons", []),
        "would_trade": False,
        "can_trade": False,
        "paper_trading_activation_allowed": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
        "would_submit": False,
        "would_close": False,
    }


def write_shadow_report(report: dict[str, Any], data_dir: Path) -> Path:
    path = shadow_report_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_and_write_shadow_report(
    *,
    data_dir: Path,
    asset: str = "XRP/USDT",
    timeframe: str = "5m",
    max_rows: int = 500,
    df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    report = build_shadow_report(data_dir=data_dir, asset=asset, timeframe=timeframe, max_rows=max_rows, df=df)
    path = write_shadow_report(report, data_dir)
    return {**report, "report_path": str(path)}
