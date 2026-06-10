from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .data import load_ohlcv
from .indicators import add_indicators
from .models import BacktestSettings, Signal, Trade, validate_entry_price
from .strategies import Strategy, default_strategies
from trading_bot.core.unified_trade_cost import UnifiedCostModel


def _ucm_scenario(cost_model: str) -> str:
    """Map clean_bot cost_model names to UnifiedCostModel scenario names."""
    return {"base": "realistic"}.get(cost_model, cost_model)


def _time(row: pd.Series) -> str:
    return str(row.get("datetime"))


def _exit_position(
    df: pd.DataFrame,
    entry_idx: int,
    signal: Signal,
    settings: BacktestSettings,
) -> tuple[int, float, str]:
    """Find exit bar, price and reason.

    Gap policy (TR-INT-02):
      BUY  gap-down at open: fill at min(open, SL)         → SL_GAP
      BUY  gap-up   at open: fill at TP (conservative)      → TP_GAP
      SELL gap-up   at open: fill at max(open, SL)          → SL_GAP
      SELL gap-down at open: fill at TP (conservative)      → TP_GAP
      SL + TP same candle:   SL wins (worst-case)           → SL_SAME_BAR
    """
    max_hold_bars = int(signal.metadata.get("max_hold_bars", settings.max_hold_bars))
    end = min(len(df) - 1, entry_idx + max_hold_bars)
    side = signal.side

    if signal.metadata.get("exit_style") == "atr_trailing":
        trail_mult = float(signal.metadata.get("trail_atr_mult", 3.0))
        trailing_stop = signal.stop_price
        for idx in range(entry_idx, end + 1):
            row = df.iloc[idx]
            open_p = float(row["Open"])
            high = float(row["High"])
            low = float(row["Low"])
            close = float(row["Close"])
            atr = float(row.get("atr14", 0.0))
            if side == "BUY":
                if open_p <= trailing_stop:
                    return idx, min(open_p, trailing_stop), "TRAIL_GAP"
                if low <= trailing_stop:
                    return idx, trailing_stop, "TRAIL"
                if atr > 0:
                    trailing_stop = max(trailing_stop, close - atr * trail_mult)
            else:
                if open_p >= trailing_stop:
                    return idx, max(open_p, trailing_stop), "TRAIL_GAP"
                if high >= trailing_stop:
                    return idx, trailing_stop, "TRAIL"
                if atr > 0:
                    trailing_stop = min(trailing_stop, close + atr * trail_mult)
        return end, float(df.iloc[end]["Close"]), "TIME_EXIT"

    for idx in range(entry_idx, end + 1):
        row = df.iloc[idx]
        open_p = float(row["Open"])
        high = float(row["High"])
        low = float(row["Low"])
        if side == "BUY":
            # Gap at open — check before intrabar logic
            if open_p <= signal.stop_price:
                return idx, min(open_p, signal.stop_price), "SL_GAP"
            if open_p >= signal.take_profit:
                return idx, signal.take_profit, "TP_GAP"
            # Normal intrabar (SL first = worst-case when both hit)
            hit_sl = low <= signal.stop_price
            hit_tp = high >= signal.take_profit
            if hit_sl and hit_tp:
                return idx, signal.stop_price, "SL_SAME_BAR"
            if hit_sl:
                return idx, signal.stop_price, "SL"
            if hit_tp:
                return idx, signal.take_profit, "TP"
        else:
            if open_p >= signal.stop_price:
                return idx, max(open_p, signal.stop_price), "SL_GAP"
            if open_p <= signal.take_profit:
                return idx, signal.take_profit, "TP_GAP"
            hit_sl = high >= signal.stop_price
            hit_tp = low <= signal.take_profit
            if hit_sl and hit_tp:
                return idx, signal.stop_price, "SL_SAME_BAR"
            if hit_sl:
                return idx, signal.stop_price, "SL"
            if hit_tp:
                return idx, signal.take_profit, "TP"
    return end, float(df.iloc[end]["Close"]), "TIME_EXIT"


def _trade_from_signal(
    *,
    df: pd.DataFrame,
    signal_idx: int,
    entry_idx: int,
    exit_idx: int,
    exit_price: float,
    exit_reason: str,
    signal: Signal,
    symbol: str,
    balance: float,
    settings: BacktestSettings,
) -> Trade:
    entry_row = df.iloc[entry_idx]
    signal_row = df.iloc[signal_idx]
    entry_price = float(entry_row["Open"])
    signal_price = float(signal_row["Close"])
    atr_pct_val = float(entry_row["atr_pct"]) if "atr_pct" in entry_row.index else 0.0

    risk_per_unit = abs(entry_price - signal.stop_price)
    if risk_per_unit <= 0:
        risk_per_unit = max(0.00000001, entry_price * 0.005)
    risk_amount = max(0.0, balance * settings.risk_per_trade_pct)
    qty_by_risk = risk_amount / risk_per_unit
    qty_by_cash = balance / entry_price
    qty = max(0.0, min(qty_by_risk, qty_by_cash))

    if signal.side == "BUY":
        gross_pnl = qty * (exit_price - entry_price)
    else:
        gross_pnl = qty * (entry_price - exit_price)

    actual_risk = max(0.00000001, qty * risk_per_unit)

    cost_result = UnifiedCostModel.apply_cost_to_backtest_trade(
        gross_pnl=gross_pnl,
        initial_risk=actual_risk,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=qty,
        scenario=_ucm_scenario(settings.cost_model),
        symbol=symbol,
        timeframe=settings.timeframe,
        atr_pct=atr_pct_val,
    )
    cost = cost_result["cost_amt"]
    net_pnl = cost_result["net_pnl"]

    gap_flag = exit_reason if "_GAP" in exit_reason else None

    return Trade(
        strategy=signal.strategy,
        symbol=symbol,
        side=signal.side,
        entry_time=_time(entry_row),
        exit_time=_time(df.iloc[exit_idx]),
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=signal.stop_price,
        take_profit=signal.take_profit,
        qty=qty,
        gross_pnl=gross_pnl,
        cost=cost,
        net_pnl=net_pnl,
        r_multiple=net_pnl / actual_risk,
        exit_reason=exit_reason,
        bars_held=max(0, exit_idx - entry_idx),
        signal_reason=signal.reason,
        signal_price=signal_price,
        fill_price=entry_price,
        entry_timing="open_n1",
        gap_flag=gap_flag,
        cost_bps_applied=cost_result.get("total_round_trip_bps"),
    )


def _metrics(trades: list[Trade], starting_balance: float) -> dict[str, Any]:
    equity = starting_balance
    peak = equity
    max_dd = 0.0
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    by_strategy: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0, "avg_r": 0.0}
    )
    r_by_strategy: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        pnl = trade.net_pnl
        wins += int(pnl > 0)
        losses += int(pnl < 0)
        gross_profit += max(0.0, pnl)
        gross_loss += abs(min(0.0, pnl))
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        bucket = by_strategy[trade.strategy]
        bucket["trades"] += 1
        bucket["pnl"] += pnl
        bucket["wins"] += int(pnl > 0)
        bucket["losses"] += int(pnl < 0)
        r_by_strategy[trade.strategy].append(trade.r_multiple)
    for strategy, values in r_by_strategy.items():
        by_strategy[strategy]["avg_r"] = sum(values) / len(values) if values else 0.0
        by_strategy[strategy]["win_rate_pct"] = (
            by_strategy[strategy]["wins"] / by_strategy[strategy]["trades"] * 100.0
            if by_strategy[strategy]["trades"]
            else 0.0
        )
    return {
        "closed_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins / len(trades) * 100.0 if trades else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "net_pnl": sum(t.net_pnl for t in trades),
        "return_pct": (equity - starting_balance) / starting_balance * 100.0 if starting_balance else 0.0,
        "ending_balance": equity,
        "max_drawdown_pct": max_dd,
        "average_r": sum(t.r_multiple for t in trades) / len(trades) if trades else 0.0,
        "by_strategy": dict(by_strategy),
    }


def run_backtest(
    *,
    data_dir: Path,
    settings: BacktestSettings,
    strategies: list[Strategy] | None = None,
) -> dict[str, Any]:
    strategies = strategies or default_strategies()
    raw = load_ohlcv(data_dir, settings.symbol, settings.timeframe, settings.max_rows)
    df = add_indicators(raw).dropna().reset_index(drop=True)
    return run_backtest_frame(raw_rows=len(raw), df=df, settings=settings, strategies=strategies)


def run_backtest_frame(
    *,
    raw_rows: int,
    df: pd.DataFrame,
    settings: BacktestSettings,
    strategies: list[Strategy],
) -> dict[str, Any]:
    trades: list[Trade] = []
    balance = settings.starting_balance
    idx = 401
    while idx < len(df) - 2:
        selected: Signal | None = None
        for strategy in strategies:
            selected = strategy.signal(df, idx)
            if selected is not None:
                break
        if selected is None:
            idx += 1
            continue
        entry_idx = idx + 1
        entry_open = float(df.iloc[entry_idx]["Open"])
        valid, reject_reason = validate_entry_price(entry_open, selected)
        if not valid:
            idx += 1
            continue
        exit_idx, exit_price, exit_reason = _exit_position(df, entry_idx, selected, settings)
        trade = _trade_from_signal(
            df=df,
            signal_idx=idx,
            entry_idx=entry_idx,
            exit_idx=exit_idx,
            exit_price=exit_price,
            exit_reason=exit_reason,
            signal=selected,
            symbol=settings.symbol,
            balance=balance,
            settings=settings,
        )
        if trade.qty <= 0:
            idx += 1
            continue
        balance += trade.net_pnl
        trades.append(trade)
        idx = max(exit_idx + 1, idx + 1)
    return {
        "report_type": "clean_bot_backtest",
        "diagnostic_only": True,
        "opens_orders": False,
        "settings": asdict(settings),
        "rows_loaded": raw_rows,
        "rows_tested": len(df),
        "strategies": [s.name for s in strategies],
        "metrics": _metrics(trades, settings.starting_balance),
        "trades": [t.to_dict() for t in trades[-200:]],
    }
