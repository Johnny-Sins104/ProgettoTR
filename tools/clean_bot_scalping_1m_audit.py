from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.clean_bot.data import cache_path, load_ohlcv
from trading_bot.clean_bot.indicators import add_indicators


@dataclass(frozen=True)
class ScalpCandidate:
    family: str
    lookback_bars: int = 20
    volume_min: float = 1.0
    stop_atr_mult: float = 1.5
    reward_atr_mult: float = 1.5
    max_hold_bars: int = 15
    trend_filter: str = "none"
    rsi_max: float = 35.0
    z_entry: float = 1.5

    @property
    def name(self) -> str:
        params = [
            self.family,
            f"lb{self.lookback_bars}",
            f"vol{self.volume_min:g}",
            f"sl{self.stop_atr_mult:g}",
            f"tp{self.reward_atr_mult:g}",
            f"hold{self.max_hold_bars}",
            self.trend_filter,
        ]
        if self.family == "mean_reversion":
            params.extend([f"rsi{self.rsi_max:g}", f"z{self.z_entry:g}"])
        return "_".join(params)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if out == out:
            return out
    except Exception:
        pass
    return default


def _profit_factor(pnls: list[float]) -> float | None:
    gross_profit = sum(max(0.0, pnl) for pnl in pnls)
    gross_loss = sum(abs(min(0.0, pnl)) for pnl in pnls)
    if gross_loss <= 0:
        return None
    return gross_profit / gross_loss


def _days_between(datetimes: np.ndarray, start: int, end: int) -> float:
    if end - start < 2:
        return 0.0
    first = pd.Timestamp(datetimes[start])
    last = pd.Timestamp(datetimes[end - 1])
    return max((last - first).total_seconds() / 86400.0, 1.0 / 1440.0)


def _prepare_frame(raw: pd.DataFrame, lookbacks: set[int]) -> pd.DataFrame:
    df = add_indicators(raw).copy()
    close = df["Close"]
    volume = df["Volume"]
    df["sma20"] = close.rolling(20).mean()
    df["std20"] = close.rolling(20).std()
    df["z20"] = (close - df["sma20"]) / df["std20"].replace(0, pd.NA)
    df["rolling_vwap_60"] = (close * volume).rolling(60).sum() / volume.rolling(60).sum().replace(0, pd.NA)
    for lookback in sorted(lookbacks):
        df[f"scalp_prior_high_{lookback}"] = df["High"].shift(1).rolling(lookback).max()
        df[f"scalp_prior_low_{lookback}"] = df["Low"].shift(1).rolling(lookback).min()
    required = [
        "datetime",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "ema20",
        "ema50",
        "ema200",
        "atr14",
        "atr_pct",
        "rsi14",
        "volume_ratio_20",
        "z20",
        "rolling_vwap_60",
        "body_ratio",
        "lower_wick_ratio",
    ]
    required.extend(f"scalp_prior_high_{lookback}" for lookback in lookbacks)
    required.extend(f"scalp_prior_low_{lookback}" for lookback in lookbacks)
    return df.dropna(subset=required).reset_index(drop=True)


def _candidate_grid() -> list[ScalpCandidate]:
    candidates: list[ScalpCandidate] = []
    for lookback in (10, 20, 30, 60):
        for volume_min in (1.0, 1.3, 1.7):
            for stop_mult in (1.0, 1.5, 2.0):
                for reward_mult in (1.0, 1.5, 2.0):
                    for hold in (5, 15, 30):
                        for trend_filter in ("none", "up"):
                            candidates.append(
                                ScalpCandidate(
                                    family="breakout",
                                    lookback_bars=lookback,
                                    volume_min=volume_min,
                                    stop_atr_mult=stop_mult,
                                    reward_atr_mult=reward_mult,
                                    max_hold_bars=hold,
                                    trend_filter=trend_filter,
                                )
                            )
    for rsi_max in (25.0, 30.0, 35.0):
        for z_entry in (1.0, 1.5, 2.0):
            for stop_mult in (1.0, 1.5, 2.0):
                for reward_mult in (0.8, 1.0, 1.5):
                    for hold in (5, 15, 30):
                        for trend_filter in ("none", "up"):
                            candidates.append(
                                ScalpCandidate(
                                    family="mean_reversion",
                                    lookback_bars=20,
                                    stop_atr_mult=stop_mult,
                                    reward_atr_mult=reward_mult,
                                    max_hold_bars=hold,
                                    trend_filter=trend_filter,
                                    rsi_max=rsi_max,
                                    z_entry=z_entry,
                                )
                            )
    for rsi_max in (45.0, 55.0, 65.0):
        for stop_mult in (1.0, 1.5, 2.0):
            for reward_mult in (1.0, 1.5, 2.0):
                for hold in (5, 15, 30):
                    candidates.append(
                        ScalpCandidate(
                            family="pullback",
                            lookback_bars=20,
                            stop_atr_mult=stop_mult,
                            reward_atr_mult=reward_mult,
                            max_hold_bars=hold,
                            trend_filter="up",
                            rsi_max=rsi_max,
                        )
                    )
    for lookback in (5, 10, 15, 20):
        for volume_min in (0.8, 1.0, 1.2):
            for stop_mult in (0.6, 0.8, 1.0):
                for reward_mult in (0.6, 0.8, 1.0):
                    for hold in (3, 5, 10):
                        for trend_filter in ("none", "up"):
                            candidates.append(
                                ScalpCandidate(
                                    family="micro_breakout",
                                    lookback_bars=lookback,
                                    volume_min=volume_min,
                                    stop_atr_mult=stop_mult,
                                    reward_atr_mult=reward_mult,
                                    max_hold_bars=hold,
                                    trend_filter=trend_filter,
                                )
                            )
    for rsi_max in (50.0, 60.0, 70.0):
        for volume_min in (0.8, 1.0, 1.2):
            for stop_mult in (0.8, 1.2, 1.6):
                for reward_mult in (0.8, 1.2, 1.6):
                    for hold in (5, 10, 20):
                        for trend_filter in ("none", "up"):
                            candidates.append(
                                ScalpCandidate(
                                    family="ema_reclaim",
                                    lookback_bars=20,
                                    volume_min=volume_min,
                                    stop_atr_mult=stop_mult,
                                    reward_atr_mult=reward_mult,
                                    max_hold_bars=hold,
                                    trend_filter=trend_filter,
                                    rsi_max=rsi_max,
                                )
                            )
    for rsi_max in (45.0, 55.0, 65.0):
        for stop_mult in (0.8, 1.2, 1.6):
            for reward_mult in (0.8, 1.2, 1.6):
                for hold in (5, 10, 20):
                    for trend_filter in ("none", "up"):
                        candidates.append(
                            ScalpCandidate(
                                family="vwap_reclaim",
                                lookback_bars=20,
                                stop_atr_mult=stop_mult,
                                reward_atr_mult=reward_mult,
                                max_hold_bars=hold,
                                trend_filter=trend_filter,
                                rsi_max=rsi_max,
                            )
                        )
    for rsi_max in (25.0, 30.0, 35.0):
        for stop_mult in (0.8, 1.2, 1.6):
            for reward_mult in (0.8, 1.2, 1.6):
                for hold in (5, 10, 20):
                    for trend_filter in ("none", "up"):
                        candidates.append(
                            ScalpCandidate(
                                family="rsi_reversal",
                                lookback_bars=20,
                                stop_atr_mult=stop_mult,
                                reward_atr_mult=reward_mult,
                                max_hold_bars=hold,
                                trend_filter=trend_filter,
                                rsi_max=rsi_max,
                            )
                        )
    return candidates


def _arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    columns = [
        "datetime",
        "Open",
        "High",
        "Low",
        "Close",
        "ema20",
        "ema50",
        "ema200",
        "atr14",
        "atr_pct",
        "rsi14",
        "volume_ratio_20",
        "z20",
        "rolling_vwap_60",
        "body_ratio",
        "lower_wick_ratio",
    ]
    out: dict[str, np.ndarray] = {"datetime": df["datetime"].to_numpy()}
    for col in columns:
        if col == "datetime":
            continue
        out[col] = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    for col in df.columns:
        if col.startswith("scalp_prior_"):
            out[col] = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    return out


def _passes_trend(arr: dict[str, np.ndarray], idx: int, trend_filter: str) -> bool:
    if trend_filter == "none":
        return True
    close = float(arr["Close"][idx])
    ema50 = float(arr["ema50"][idx])
    ema200 = float(arr["ema200"][idx])
    return close > ema50 > ema200


def _signal_long(arr: dict[str, np.ndarray], idx: int, candidate: ScalpCandidate) -> tuple[float, float] | None:
    close = float(arr["Close"][idx])
    high = float(arr["High"][idx])
    low = float(arr["Low"][idx])
    ema20 = float(arr["ema20"][idx])
    ema50 = float(arr["ema50"][idx])
    ema200 = float(arr["ema200"][idx])
    atr = float(arr["atr14"][idx])
    atr_pct = float(arr["atr_pct"][idx])
    rsi = float(arr["rsi14"][idx])
    volume_ratio = float(arr["volume_ratio_20"][idx])
    z20 = float(arr["z20"][idx])
    if min(close, high, low, atr) <= 0 or not (0.01 <= atr_pct <= 2.0):
        return None
    if not _passes_trend(arr, idx, candidate.trend_filter):
        return None

    if candidate.family == "breakout":
        prior_high = float(arr[f"scalp_prior_high_{candidate.lookback_bars}"][idx])
        closes_near_high = (high - close) <= atr * 0.35
        if close > prior_high and volume_ratio >= candidate.volume_min and closes_near_high:
            return close - atr * candidate.stop_atr_mult, close + atr * candidate.reward_atr_mult
        return None

    if candidate.family == "mean_reversion":
        prior_low = float(arr[f"scalp_prior_low_{candidate.lookback_bars}"][idx])
        stretched_down = z20 <= -candidate.z_entry and rsi <= candidate.rsi_max
        capitulation_near_low = close <= prior_low + atr * 0.80
        if stretched_down and capitulation_near_low:
            return close - atr * candidate.stop_atr_mult, close + atr * candidate.reward_atr_mult
        return None

    if candidate.family == "pullback":
        if ema20 > ema50 > ema200 and low <= ema20 and close > ema20 and rsi <= candidate.rsi_max:
            return close - atr * candidate.stop_atr_mult, close + atr * candidate.reward_atr_mult
        return None

    return None


def _signal_indices(arr: dict[str, np.ndarray], candidate: ScalpCandidate, *, start: int, end: int) -> np.ndarray:
    close = arr["Close"]
    high = arr["High"]
    low = arr["Low"]
    ema20 = arr["ema20"]
    ema50 = arr["ema50"]
    ema200 = arr["ema200"]
    atr = arr["atr14"]
    atr_pct = arr["atr_pct"]
    rsi = arr["rsi14"]
    volume_ratio = arr["volume_ratio_20"]
    z20 = arr["z20"]
    rolling_vwap_60 = arr["rolling_vwap_60"]
    body_ratio = arr["body_ratio"]
    lower_wick_ratio = arr["lower_wick_ratio"]
    base = (
        np.isfinite(close)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(atr)
        & (close > 0)
        & (high > 0)
        & (low > 0)
        & (atr > 0)
        & (atr_pct >= 0.01)
        & (atr_pct <= 2.0)
    )
    if candidate.trend_filter == "up":
        base = base & (close > ema50) & (ema50 > ema200)

    if candidate.family == "breakout":
        prior_high = arr[f"scalp_prior_high_{candidate.lookback_bars}"]
        closes_near_high = (high - close) <= atr * 0.35
        mask = base & (close > prior_high) & (volume_ratio >= candidate.volume_min) & closes_near_high
    elif candidate.family == "micro_breakout":
        prior_high = arr[f"scalp_prior_high_{candidate.lookback_bars}"]
        closes_near_high = (high - close) <= atr * 0.55
        mask = base & (close > prior_high) & (volume_ratio >= candidate.volume_min) & closes_near_high
    elif candidate.family == "mean_reversion":
        prior_low = arr[f"scalp_prior_low_{candidate.lookback_bars}"]
        mask = base & (z20 <= -candidate.z_entry) & (rsi <= candidate.rsi_max) & (close <= prior_low + atr * 0.80)
    elif candidate.family == "pullback":
        mask = base & (ema20 > ema50) & (ema50 > ema200) & (low <= ema20) & (close > ema20) & (rsi <= candidate.rsi_max)
    elif candidate.family == "ema_reclaim":
        prev_close = np.roll(close, 1)
        prev_ema20 = np.roll(ema20, 1)
        reclaim = (prev_close <= prev_ema20) & (close > ema20)
        healthy_rsi = (rsi >= 35.0) & (rsi <= candidate.rsi_max)
        mask = base & reclaim & healthy_rsi & (volume_ratio >= candidate.volume_min)
    elif candidate.family == "vwap_reclaim":
        prev_close = np.roll(close, 1)
        prev_vwap = np.roll(rolling_vwap_60, 1)
        reclaim = (prev_close <= prev_vwap) & (close > rolling_vwap_60)
        mask = base & reclaim & (rsi <= candidate.rsi_max)
    elif candidate.family == "rsi_reversal":
        prev_close = np.roll(close, 1)
        reversal = (rsi <= candidate.rsi_max) & (close > prev_close) & (lower_wick_ratio >= 0.25) & (body_ratio >= 0.10)
        mask = base & reversal
    else:
        mask = np.zeros_like(close, dtype=bool)

    left = max(start, 220)
    right = max(left, end - 2)
    if right <= left:
        return np.array([], dtype=np.int64)
    return np.flatnonzero(mask[left:right]) + left


def _run_candidate(
    arr: dict[str, np.ndarray],
    candidate: ScalpCandidate,
    *,
    start: int,
    end: int,
    starting_balance: float,
    risk_per_trade_pct: float,
    round_trip_bps: float,
) -> dict[str, Any]:
    equity = float(starting_balance)
    peak = equity
    max_dd = 0.0
    pnls: list[float] = []
    r_values: list[float] = []
    wins = 0
    losses = 0
    first_trade = ""
    last_trade = ""
    next_allowed_idx = max(start, 220)
    for idx in _signal_indices(arr, candidate, start=start, end=end):
        if equity <= 0:
            break
        if idx < next_allowed_idx:
            continue
        close = float(arr["Close"][idx])
        atr = float(arr["atr14"][idx])
        stop_price = close - atr * candidate.stop_atr_mult
        take_profit = close + atr * candidate.reward_atr_mult
        entry_idx = idx + 1
        if entry_idx >= end:
            break
        entry_price = float(arr["Open"][entry_idx])
        risk_per_unit = abs(entry_price - stop_price)
        if entry_price <= 0 or risk_per_unit <= 0:
            continue
        risk_amount = max(0.0, equity * risk_per_trade_pct)
        qty = min(risk_amount / risk_per_unit, equity / entry_price)
        if qty <= 0:
            continue
        exit_idx = entry_idx
        exit_price = float(arr["Close"][entry_idx])
        exit_end = min(end - 1, entry_idx + candidate.max_hold_bars)
        for pos in range(entry_idx, exit_end + 1):
            low = float(arr["Low"][pos])
            high = float(arr["High"][pos])
            if low <= stop_price:
                exit_idx = pos
                exit_price = stop_price
                break
            if high >= take_profit:
                exit_idx = pos
                exit_price = take_profit
                break
            exit_idx = pos
            exit_price = float(arr["Close"][pos])
        gross_pnl = qty * (exit_price - entry_price)
        cost = abs(qty * entry_price) * round_trip_bps / 10000.0
        net_pnl = gross_pnl - cost
        actual_risk = max(0.00000001, qty * risk_per_unit)
        pnls.append(net_pnl)
        r_values.append(net_pnl / actual_risk)
        wins += int(net_pnl > 0)
        losses += int(net_pnl < 0)
        equity += net_pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        if not first_trade:
            first_trade = str(pd.Timestamp(arr["datetime"][entry_idx]))
        last_trade = str(pd.Timestamp(arr["datetime"][exit_idx]))
        next_allowed_idx = max(exit_idx + 1, idx + 1)
    days = _days_between(arr["datetime"], start, end)
    pf = _profit_factor(pnls)
    return {
        "closed_trades": len(pnls),
        "trades_per_day": len(pnls) / days if days else 0.0,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins / len(pnls) * 100.0 if pnls else 0.0,
        "net_pnl": sum(pnls),
        "return_pct": (equity - starting_balance) / starting_balance * 100.0 if starting_balance else 0.0,
        "ending_balance": equity,
        "profit_factor": pf,
        "max_drawdown_pct": max_dd,
        "average_r": sum(r_values) / len(r_values) if r_values else 0.0,
        "first_trade": first_trade,
        "last_trade": last_trade,
    }


def _target_status(
    row: dict[str, Any],
    *,
    min_trades_per_day: float,
    max_trades_per_day: float,
    max_drawdown_pct: float,
) -> str:
    train = row["train"]
    validation = row["validation"]
    validation_severe = row["validation_severe"]
    train_pf = _pf_value(train)
    validation_pf = _pf_value(validation)
    severe_pf = _pf_value(validation_severe)
    in_frequency = (
        min_trades_per_day <= train["trades_per_day"] <= max_trades_per_day
        and min_trades_per_day <= validation["trades_per_day"] <= max_trades_per_day
    )
    profitable = (
        train["return_pct"] > 0
        and validation["return_pct"] > 0
        and validation_severe["return_pct"] > 0
        and train_pf >= 1.05
        and validation_pf >= 1.05
        and severe_pf >= 1.00
    )
    controlled_dd = validation["max_drawdown_pct"] <= max_drawdown_pct
    if in_frequency and profitable and controlled_dd:
        return "TARGET_PAPER_CANDIDATE"
    if validation["return_pct"] > 0 and validation_pf >= 1.00:
        return "POSITIVE_BUT_NOT_TARGET"
    return "REJECTED"


def _score(row: dict[str, Any], *, min_trades_per_day: float, max_trades_per_day: float) -> float:
    validation = row["validation"]
    train = row["train"]
    target_mid = (min_trades_per_day + max_trades_per_day) / 2.0
    freq_penalty = abs(validation["trades_per_day"] - target_mid) * 2.0
    return (
        validation["return_pct"]
        + min(train["return_pct"], validation["return_pct"])
        + min(_pf_value(validation), 5.0) * 2.0
        - validation["max_drawdown_pct"] * 0.35
        - freq_penalty
    )


def _pf_value(metrics: dict[str, Any]) -> float:
    pf = metrics.get("profit_factor")
    if pf is None and metrics.get("closed_trades", 0) and metrics.get("return_pct", 0.0) > 0:
        return 999.0
    return _float(pf)


def build_report(
    *,
    data_dir: Path,
    symbol: str,
    balance: float,
    risk_per_trade_pct: float,
    max_rows: int,
    slippage_bps: float,
    severe_slippage_bps: float,
    min_trades_per_day: float,
    max_trades_per_day: float,
    max_drawdown_pct: float,
    top_n: int,
) -> dict[str, Any]:
    raw = load_ohlcv(data_dir, symbol, "1m", max_rows=max_rows)
    candidates = _candidate_grid()
    lookbacks = {candidate.lookback_bars for candidate in candidates}
    df = _prepare_frame(raw, lookbacks)
    if len(df) < 2500:
        raise RuntimeError(f"not_enough_1m_rows:{len(df)}")
    arr = _arrays(df)
    split = len(df) // 2
    train_start = 0
    train_end = split
    validation_start = split
    validation_end = len(df)
    conservative_bps = 13.0 + slippage_bps
    severe_bps = 29.0 + severe_slippage_bps

    train_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        train = _run_candidate(
            arr,
            candidate,
            start=train_start,
            end=train_end,
            starting_balance=balance,
            risk_per_trade_pct=risk_per_trade_pct,
            round_trip_bps=conservative_bps,
        )
        if train["closed_trades"] < 5:
            continue
        train_rows.append({"candidate": candidate, "train": train})
    train_rows.sort(
        key=lambda row: (
            row["train"]["return_pct"],
            min(_pf_value(row["train"]), 5.0),
            -abs(row["train"]["trades_per_day"] - ((min_trades_per_day + max_trades_per_day) / 2.0)),
        ),
        reverse=True,
    )
    target_frequency_train = [
        row
        for row in train_rows
        if min_trades_per_day <= row["train"]["trades_per_day"] <= max_trades_per_day
    ]
    target_train = [
        row
        for row in target_frequency_train
        if row["train"]["return_pct"] > 0 and _pf_value(row["train"]) >= 1.05
    ]
    target_frequency_train.sort(
        key=lambda row: (
            row["train"]["return_pct"],
            min(_pf_value(row["train"]), 5.0),
        ),
        reverse=True,
    )
    selected_by_name: dict[str, dict[str, Any]] = {}
    for row in target_frequency_train[: min(len(target_frequency_train), max(75, top_n * 8))]:
        selected_by_name[row["candidate"].name] = row
    for row in target_train:
        selected_by_name[row["candidate"].name] = row
    for row in train_rows[: min(len(train_rows), max(150, top_n * 12))]:
        selected_by_name.setdefault(row["candidate"].name, row)
    selected = list(selected_by_name.values())

    evaluated: list[dict[str, Any]] = []
    for item in selected:
        candidate = item["candidate"]
        validation = _run_candidate(
            arr,
            candidate,
            start=validation_start,
            end=validation_end,
            starting_balance=balance,
            risk_per_trade_pct=risk_per_trade_pct,
            round_trip_bps=conservative_bps,
        )
        validation_severe = _run_candidate(
            arr,
            candidate,
            start=validation_start,
            end=validation_end,
            starting_balance=balance,
            risk_per_trade_pct=risk_per_trade_pct,
            round_trip_bps=severe_bps,
        )
        full = _run_candidate(
            arr,
            candidate,
            start=0,
            end=len(df),
            starting_balance=balance,
            risk_per_trade_pct=risk_per_trade_pct,
            round_trip_bps=conservative_bps,
        )
        row = {
            "name": candidate.name,
            "strategy": asdict(candidate),
            "train": item["train"],
            "validation": validation,
            "validation_severe": validation_severe,
            "full": full,
        }
        row["status"] = _target_status(
            row,
            min_trades_per_day=min_trades_per_day,
            max_trades_per_day=max_trades_per_day,
            max_drawdown_pct=max_drawdown_pct,
        )
        row["score"] = _score(row, min_trades_per_day=min_trades_per_day, max_trades_per_day=max_trades_per_day)
        evaluated.append(row)

    evaluated.sort(key=lambda row: (row["status"] == "TARGET_PAPER_CANDIDATE", row["score"]), reverse=True)
    accepted = [row for row in evaluated if row["status"] == "TARGET_PAPER_CANDIDATE"]
    positive = [row for row in evaluated if row["status"] == "POSITIVE_BUT_NOT_TARGET"]
    rejected = [row for row in evaluated if row["status"] == "REJECTED"]
    target_frequency_validated = [
        row
        for row in evaluated
        if min_trades_per_day <= row["train"]["trades_per_day"] <= max_trades_per_day
        or min_trades_per_day <= row["validation"]["trades_per_day"] <= max_trades_per_day
    ]
    target_frequency_validated.sort(key=lambda row: row["validation"]["return_pct"], reverse=True)
    output_path = cache_path(data_dir, symbol, "1m")
    return {
        "report_type": "clean_bot_scalping_1m_audit",
        "diagnostic_only": True,
        "opens_orders": False,
        "target": f"{min_trades_per_day:g}-{max_trades_per_day:g} long-only spot-style trades/day, profitable in validation after costs",
        "target_status": "FOUND" if accepted else "NOT_FOUND",
        "settings": {
            "symbol": symbol,
            "timeframe": "1m",
            "balance": balance,
            "risk_per_trade_pct": risk_per_trade_pct,
            "max_rows": max_rows,
            "conservative_round_trip_bps": conservative_bps,
            "severe_round_trip_bps": severe_bps,
            "min_trades_per_day": min_trades_per_day,
            "max_trades_per_day": max_trades_per_day,
            "max_drawdown_pct": max_drawdown_pct,
            "cache_path": str(output_path),
        },
        "data": {
            "raw_rows": len(raw),
            "tested_rows": len(df),
            "start": str(pd.Timestamp(df["datetime"].iloc[0])),
            "end": str(pd.Timestamp(df["datetime"].iloc[-1])),
            "days": _days_between(arr["datetime"], 0, len(df)),
            "train_days": _days_between(arr["datetime"], train_start, train_end),
            "validation_days": _days_between(arr["datetime"], validation_start, validation_end),
        },
        "scan": {
            "candidate_count": len(candidates),
            "train_survivors": len(train_rows),
            "target_frequency_train_count": len(target_frequency_train),
            "validated_count": len(evaluated),
            "accepted_count": len(accepted),
            "positive_but_not_target_count": len(positive),
        },
        "accepted": accepted[:top_n],
        "positive_but_not_target": positive[:top_n],
        "target_frequency_rejected": target_frequency_validated[:top_n],
        "top_rejected": rejected[:top_n],
        "top_validated": evaluated[:top_n],
        "decision": (
            "Do not integrate a 1m scalping profile unless accepted_count is greater than zero."
            if not accepted
            else "Eligible only for supervised paper observation before any live discussion."
        ),
    }


def _fmt_pf(value: Any) -> str:
    return "-" if value is None else f"{_float(value):.2f}"


def _fmt_metrics(metrics: dict[str, Any]) -> str:
    return (
        f"ret={metrics['return_pct']:+.2f}% pf={_fmt_pf(metrics.get('profit_factor'))} "
        f"trades={metrics['closed_trades']} tpd={metrics['trades_per_day']:.2f} "
        f"dd={metrics['max_drawdown_pct']:.2f}%"
    )


def _row_line(row: dict[str, Any]) -> str:
    return (
        f"  {row['status']} {row['name']}: "
        f"train[{_fmt_metrics(row['train'])}] "
        f"valid[{_fmt_metrics(row['validation'])}] "
        f"severe_valid[{_fmt_metrics(row['validation_severe'])}]"
    )


def format_report(report: dict[str, Any]) -> str:
    settings = report["settings"]
    data = report["data"]
    scan = report["scan"]
    lines = [
        "CLEAN BOT 1M SCALPING AUDIT",
        f"target={report['target']} status={report['target_status']}",
        f"symbol={settings['symbol']} rows={data['tested_rows']} days={data['days']:.1f} start={data['start']} end={data['end']}",
        f"costs=conservative {settings['conservative_round_trip_bps']:.1f}bps / severe {settings['severe_round_trip_bps']:.1f}bps",
        f"scan=candidates {scan['candidate_count']} train_survivors {scan['train_survivors']} "
        f"target_freq_train {scan['target_frequency_train_count']} validated {scan['validated_count']} accepted {scan['accepted_count']}",
        "",
    ]
    if report["accepted"]:
        lines.append("accepted:")
        for row in report["accepted"]:
            lines.append(_row_line(row))
        lines.append("")
    if report["positive_but_not_target"]:
        lines.append("positive_but_not_target:")
        for row in report["positive_but_not_target"]:
            lines.append(_row_line(row))
        lines.append("")
    if report["target_frequency_rejected"]:
        lines.append("target_frequency_rejected:")
        for row in report["target_frequency_rejected"]:
            lines.append(_row_line(row))
        lines.append("")
    lines.append("top_validated:")
    for row in report["top_validated"]:
        lines.append(_row_line(row))
    lines.append("")
    lines.append(f"decision={report['decision']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit 1m spot-style scalping candidates for the clean bot.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--symbol", default="XRP/USDT")
    parser.add_argument("--balance", type=float, default=100.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.01)
    parser.add_argument("--max-rows", type=int, default=150000)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--severe-slippage-bps", type=float, default=8.0)
    parser.add_argument("--min-trades-per-day", type=float, default=3.0)
    parser.add_argument("--max-trades-per-day", type=float, default=4.5)
    parser.add_argument("--max-drawdown-pct", type=float, default=25.0)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", default="data/clean_bot_scalping_1m_audit.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(
        data_dir=Path(args.data_dir),
        symbol=args.symbol,
        balance=args.balance,
        risk_per_trade_pct=args.risk_per_trade_pct,
        max_rows=args.max_rows,
        slippage_bps=args.slippage_bps,
        severe_slippage_bps=args.severe_slippage_bps,
        min_trades_per_day=args.min_trades_per_day,
        max_trades_per_day=args.max_trades_per_day,
        max_drawdown_pct=args.max_drawdown_pct,
        top_n=max(1, args.top),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
