from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from trading_bot.dashboard.strategy_dashboard_state import DISPLAY_NAMES
from trading_bot.strategies import strategy_factory
from trading_bot.strategy_runtime.strategy_config_store import load_runtime_config
from trading_bot.strategy_runtime.strategy_signal_schema import SUPPORTED_STRATEGIES, make_signal, validate_strategy_id


MarketDataLoader = Callable[[Path, str, str, int], pd.DataFrame]
StrategyFactory = Callable[[str, dict[str, Any] | None], Any]


def _safe_wait(strategy: str, reason: str, *, label: str = "") -> dict[str, Any]:
    return make_signal(
        strategy=strategy,
        strategy_label=label or DISPLAY_NAMES.get(strategy, strategy),
        signal="WAIT",
        score=0.0,
        conditions=[],
        entry_price=None,
        sl=None,
        tp=None,
        risk_pct=None,
        blocked=True,
        block_reasons=[reason, "shadow_signal_execution_only"],
        shadow_only=True,
        would_trade=False,
        can_trade=False,
    )


def _read_active_strategy(data_dir: Path) -> tuple[str, str]:
    try:
        config = load_runtime_config(data_dir, create=False)
        strategy = validate_strategy_id(str(config.get("active_strategy", "")))
        return strategy, ""
    except ValueError as exc:
        if "unsupported_strategy" not in str(exc):
            return "invalid", "runtime_strategy_config_unreadable"
        return "invalid", "invalid_active_strategy"
    except Exception:
        return "invalid", "runtime_strategy_config_unreadable"


def _load_market_data(
    data_dir: Path,
    *,
    asset: str,
    timeframe: str,
    max_rows: int,
    market_data_loader: MarketDataLoader | None,
) -> pd.DataFrame | None:
    if market_data_loader is not None:
        return market_data_loader(data_dir, asset, timeframe, max_rows)
    try:
        from trading_bot.clean_bot.data import load_ohlcv

        return load_ohlcv(data_dir, asset, timeframe, max_rows=max_rows)
    except Exception:
        return None


def enforce_shadow(signal: dict[str, Any], *, strategy: str) -> dict[str, Any]:
    out = dict(signal)
    reasons = list(out.get("block_reasons") or [])
    if "shadow_signal_execution_only" not in reasons:
        reasons.append("shadow_signal_execution_only")
    out.update(
        {
            "strategy": strategy,
            "strategy_label": DISPLAY_NAMES.get(strategy, strategy),
            "blocked": True,
            "block_reasons": reasons,
            "shadow_only": True,
            "would_trade": False,
            "can_trade": False,
        }
    )
    return out


def execute_shadow_signal(
    data_dir: Path,
    *,
    asset: str = "XRP/USDT",
    timeframe: str = "5m",
    max_rows: int = 500,
    df: pd.DataFrame | None = None,
    params: dict[str, Any] | None = None,
    market_data_loader: MarketDataLoader | None = None,
    strategy_factory_fn: StrategyFactory | None = None,
) -> dict[str, Any]:
    active, config_error = _read_active_strategy(data_dir)
    if config_error:
        return {
            "active_strategy": active,
            "active_strategy_label": "Invalid",
            "evaluated_strategies": [],
            "single_strategy_execution_confirmed": True,
            "signal": _safe_wait(active, config_error, label="Invalid"),
        }
    if active == "auto":
        return {
            "active_strategy": "auto",
            "active_strategy_label": DISPLAY_NAMES["auto"],
            "evaluated_strategies": [],
            "single_strategy_execution_confirmed": True,
            "auto_strategy_execution_allowed": False,
            "signal": _safe_wait("auto", "auto_strategy_shadow_disabled", label=DISPLAY_NAMES["auto"]),
        }
    if active not in SUPPORTED_STRATEGIES:
        return {
            "active_strategy": active,
            "active_strategy_label": "Invalid",
            "evaluated_strategies": [],
            "single_strategy_execution_confirmed": True,
            "signal": _safe_wait(active, "invalid_active_strategy", label="Invalid"),
        }
    frame = df if df is not None else _load_market_data(
        data_dir,
        asset=asset,
        timeframe=timeframe,
        max_rows=max_rows,
        market_data_loader=market_data_loader,
    )
    if frame is None or len(frame) < 2:
        return {
            "active_strategy": active,
            "active_strategy_label": DISPLAY_NAMES.get(active, active),
            "evaluated_strategies": [active],
            "single_strategy_execution_confirmed": True,
            "signal": _safe_wait(active, "market_data_unavailable", label=DISPLAY_NAMES.get(active, active)),
        }
    factory = strategy_factory_fn or strategy_factory
    try:
        strategy = factory(active, params)
        raw_signal = strategy.evaluate(frame, asset=asset, timeframe=timeframe)
    except Exception as exc:
        return {
            "active_strategy": active,
            "active_strategy_label": DISPLAY_NAMES.get(active, active),
            "evaluated_strategies": [active],
            "single_strategy_execution_confirmed": True,
            "signal": _safe_wait(active, f"shadow_strategy_error:{exc}", label=DISPLAY_NAMES.get(active, active)),
        }
    return {
        "active_strategy": active,
        "active_strategy_label": DISPLAY_NAMES.get(active, active),
        "evaluated_strategies": [active],
        "single_strategy_execution_confirmed": True,
        "auto_strategy_execution_allowed": False,
        "signal": enforce_shadow(raw_signal, strategy=active),
    }
