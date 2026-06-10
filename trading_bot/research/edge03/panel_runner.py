"""panel_runner.py — Thin panel-run scaffold for Edge Research 03.

The point-in-time panel loader lives on strat/edge-research-02 (user's PC):
it is INJECTED here as a callable, so this module has no dependency on that
branch's internals. Reconcile the loader signature at merge time.

Contract of the injected callables:
  panel_loader(symbol: str, timeframe: str) -> pd.DataFrame
      Indicator-ready OHLCV frame (datetime, Open, High, Low, Close, Volume,
      atr14, atr_pct, ... as required by the strategy family).
  funding_loader(symbol: str) -> pd.DataFrame
      Validated funding frame per clean_bot/funding.py (only required for
      carry runs: settings.funding_enabled=True is then mandatory).

Every run goes through assert_declared() first: undeclared configs raise.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from trading_bot.clean_bot.backtest import run_backtest_frame
from trading_bot.clean_bot.models import BacktestSettings
from trading_bot.clean_bot.strategies import Strategy
from trading_bot.clean_bot.validation_gates import (
    PANEL_VALIDATION_CONFIG,
    is_promising_panel,
)

from .declared_trials import assert_declared

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False


def run_trial_on_panel(
    *,
    family: str,
    config: Any,
    strategy_factory: Callable[[Any, str], Strategy],
    symbols: list[str],
    timeframe: str,
    panel_loader: Callable[[str, str], pd.DataFrame],
    funding_loader: Callable[[str], pd.DataFrame] | None = None,
    starting_balance: float = 1000.0,
) -> dict[str, Any]:
    """Run one declared config across the panel and apply the pooled gate.

    strategy_factory(config, symbol) builds the Strategy instance (the carry
    family needs the symbol's funding series at construction).
    Returns a per-trial report: per-symbol metrics/trades plus the pooled
    is_promising_panel verdict. Raises on undeclared configs (fail-closed).
    """
    trial_number = assert_declared(family, config)

    if not symbols:
        raise ValueError("symbols must be a non-empty panel list")
    tf = str(timeframe or "").lower().strip()

    per_symbol: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        df = panel_loader(symbol, tf)
        funding_df = funding_loader(symbol) if funding_loader is not None else None
        settings = BacktestSettings(
            symbol=symbol,
            timeframe=tf,
            starting_balance=starting_balance,
            risk_per_trade_pct=float(PANEL_VALIDATION_CONFIG["risk_per_trade_pct"]),
            cost_model=str(PANEL_VALIDATION_CONFIG["cost_scenario"]),
            funding_enabled=funding_df is not None,
        )
        strategy = strategy_factory(config, symbol)
        result = run_backtest_frame(
            raw_rows=len(df),
            df=df,
            settings=settings,
            strategies=[strategy],
            funding_df=funding_df,
        )
        per_symbol[symbol] = {
            "metrics": result["metrics"],
            "trades": result["trades"],
        }

    passes, checks = is_promising_panel(per_symbol)
    return {
        "report_type": "edge03_panel_trial",
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "trial_number": trial_number,
        "family": family,
        "timeframe": tf,
        "symbols": list(symbols),
        "panel_gate": {"passes": passes, "checks": checks},
        "per_symbol": per_symbol,
    }
