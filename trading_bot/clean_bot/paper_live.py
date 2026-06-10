from __future__ import annotations

import json
import asyncio
import os
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.core.client import ExchangeClient
from trading_bot.core.paper_market_data import CachedMarketDataNotFound, load_cached_ohlcv
from trading_bot.core.unified_trade_cost import UnifiedCostModel

from .indicators import add_indicators
from .models import Signal, validate_entry_price
from .strategies import strategy_profile


def load_paper_env(dotenv_path: str | None = None) -> bool:
    """Load project .env without logging or returning secret values.

    Idempotent and best-effort: if python-dotenv is absent the call is a no-op.
    Uses override=False so existing environment variables are never overwritten.
    Returns True if dotenv was loaded, False if python-dotenv is not installed.
    """
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        kwargs: dict[str, Any] = {"override": False}
        if dotenv_path is not None:
            kwargs["dotenv_path"] = dotenv_path
        load_dotenv(**kwargs)
        return True
    except ImportError:
        return False


# Load project .env at module import (best-effort — no secrets in logs or output)
load_paper_env()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ucm_scenario(cost_model: str) -> str:
    """Map clean_bot cost_model name to UnifiedCostModel scenario name."""
    return {"base": "realistic"}.get(cost_model, cost_model)


@dataclass(frozen=True)
class CleanPaperSettings:
    symbol: str = "XRP/USDT"
    timeframe: str = "5m"
    data_dir: str = "data"
    market_data_mode: str = "auto"
    balance: float = 100.0
    risk_per_trade_pct: float = 0.005
    cost_model: str = "conservative"
    profile: str = "active"
    candle_limit: int = 1500
    poll_seconds: float = 60.0
    max_cycles: int = 0
    telegram_enabled: bool = False
    telegram_notify_every_cycle: bool = False


def _state_path(settings: CleanPaperSettings) -> Path:
    return Path(settings.data_dir) / "clean_paper_state.json"


def _events_path(settings: CleanPaperSettings) -> Path:
    return Path(settings.data_dir) / "clean_paper_events.jsonl"


def _default_state(settings: CleanPaperSettings) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "profile": settings.profile,
        "initial_balance": settings.balance,
        "cash": settings.balance,
        "realized_pnl": 0.0,
        "position": None,
        "pending_order": None,
        "closed_trades": [],
        "last_processed_bar": "",
    }


def _read_state(settings: CleanPaperSettings) -> dict[str, Any]:
    path = _state_path(settings)
    if not path.exists():
        return _default_state(settings)
    try:
        text = path.read_text(encoding="utf-8")
        state = json.loads(text)
        if not isinstance(state, dict):
            raise ValueError(f"state root is {type(state).__name__}, expected dict")
        return state
    except Exception as exc:
        # Create a backup of the corrupt file before any recovery operation.
        # If the backup write fails, propagate the exception — fail-closed.
        bak = path.with_suffix(".bak")
        bak.write_bytes(path.read_bytes())
        # write_bytes can complete without raising yet fail to persist the file
        # (e.g. on certain virtual/overlay filesystems). Fail-closed: never proceed
        # with recovery unless the backup is verified to exist on disk.
        if not bak.exists():
            raise RuntimeError(f"backup file not created after write_bytes: {bak}")
        # File exists but is corrupt: return default WITH detectable flag.
        # Do NOT silently lose an open position — callers and tests can inspect _corrupt_recovery.
        state = _default_state(settings)
        state["_corrupt_recovery"] = True
        state["_corrupt_error"] = str(exc)
        try:
            _emit(settings, "CLEAN_STATE_CORRUPT_RECOVERY",
                  error=str(exc), path=str(path), backup=str(bak))
        except Exception:
            pass
        return state


def _write_state(settings: CleanPaperSettings, state: dict[str, Any]) -> None:
    """Atomic write: write to .tmp then os.replace — crash-safe on NTFS."""
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["profile"] = settings.profile
    state["updated_at"] = utc_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _emit(settings: CleanPaperSettings, event_type: str, **payload: Any) -> None:
    path = _events_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": utc_now(), "event_type": event_type, **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _send_telegram(settings: CleanPaperSettings, text: str, *, force: bool = False) -> dict[str, Any]:
    if not settings.telegram_enabled:
        return {"ok": False, "reason": "telegram_disabled"}

    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"ok": False, "reason": "missing_TELEGRAM_TOKEN_or_TELEGRAM_CHAT_ID"}
    if not force and (token == "IL_TUO_TOKEN" or chat_id == "IL_TUO_CHAT_ID"):
        return {"ok": False, "reason": "placeholder_telegram_values"}
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"ok": 200 <= int(response.status) < 300, "status": int(response.status)}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body = ""
        return {"ok": False, "reason": "telegram_http_error", "status": int(exc.code), "body": body}
    except Exception as exc:
        return {"ok": False, "reason": "telegram_send_error", "error": str(exc)}


def send_telegram_test(settings: CleanPaperSettings) -> dict[str, Any]:
    return _send_telegram(
        settings,
        f"CLEAN PAPER TELEGRAM TEST OK {settings.symbol} {utc_now()}",
        force=False,
    )


def _frame_from_exchange(settings: CleanPaperSettings) -> pd.DataFrame:
    client = ExchangeClient(symbol=settings.symbol, timeframe=settings.timeframe, limit=settings.candle_limit)
    df = asyncio.run(client.fetch_async()).reset_index()
    return df.rename(columns={"timestamp": "datetime"})


def _frame_from_cache(settings: CleanPaperSettings) -> pd.DataFrame:
    market = load_cached_ohlcv(
        data_dir=settings.data_dir,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        limit=settings.candle_limit,
    )
    return market.df.reset_index()


def load_market_frame(settings: CleanPaperSettings) -> tuple[pd.DataFrame, str]:
    mode = settings.market_data_mode
    if mode == "cache":
        return _frame_from_cache(settings), "cache"
    if mode == "live":
        return _frame_from_exchange(settings), "live"
    try:
        return _frame_from_exchange(settings), "live"
    except Exception:
        try:
            return _frame_from_cache(settings), "cache"
        except CachedMarketDataNotFound:
            raise


def _prepared_frame(settings: CleanPaperSettings) -> tuple[pd.DataFrame, str]:
    raw, source = load_market_frame(settings)
    required = {"datetime", "Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"market frame missing columns: {missing}")
    raw = raw.sort_values("datetime").tail(settings.candle_limit).reset_index(drop=True)
    prepared = add_indicators(raw)
    lookback = 288 if str(settings.profile).strip().lower() == "active" else 576
    needed = [
        "Open", "High", "Low", "Close", "Volume",
        "ema50", "ema200", "atr14", "atr_pct", "volume_ratio_20",
        f"prior_high_{lookback}",
    ]
    return prepared.dropna(subset=needed).reset_index(drop=True), source


def _signal(settings: CleanPaperSettings, df: pd.DataFrame) -> tuple[Signal | None, pd.Series]:
    if len(df) < 10:
        raise ValueError("not enough candles after indicators")
    idx = max(0, len(df) - 2)
    strategy = strategy_profile(settings.profile)[0]
    return strategy.signal(df, idx), df.iloc[idx]


def _equity(state: dict[str, Any], last_price: float) -> float:
    cash = float(state.get("cash", 0.0))
    position = state.get("position")
    if not isinstance(position, dict):
        return cash
    return cash + float(position.get("qty", 0.0)) * last_price


def _atr_pct_from_row(row: pd.Series) -> float:
    if "atr_pct" in row.index:
        return max(0.0, float(row["atr_pct"]))
    atr = float(row["atr14"]) if "atr14" in row.index else 0.0
    close = float(row["Close"]) if "Close" in row.index else 1.0
    return atr / close if close > 0 else 0.0


def _close_position(
    settings: CleanPaperSettings,
    state: dict[str, Any],
    exit_price: float,
    reason: str,
    bar_time: str,
) -> dict[str, Any]:
    position = state.get("position")
    if not isinstance(position, dict):
        return {}
    qty = float(position["qty"])
    entry_price = float(position["entry_price"])
    # Use original stop for R calculation; fall back to current stop_loss
    stop_price = float(position.get("stop_price_at_entry", position["stop_loss"]))
    atr_pct_val = float(position.get("atr_pct_at_entry", 0.0))
    side = str(position.get("side", "BUY")).upper()
    cost_basis = float(position["cost_basis"])  # = qty * entry_price (no entry fee)

    try:
        outcome = UnifiedCostModel.compute_trade_outcome(
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_price=stop_price,
            quantity=qty,
            scenario=_ucm_scenario(settings.cost_model),
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            atr_pct=atr_pct_val,
        )
    except ValueError as exc:
        # UCM fail-closed: state, cash and position remain unchanged.
        # No free trades, no silent close. Emit a verifiable error event.
        _emit(settings, "CLEAN_UCM_ERROR",
              error=str(exc),
              position_id=str(position.get("position_id", "")),
              exit_price=exit_price,
              reason=reason,
              bar_time=bar_time)
        return {"action": "UCM_FAIL_CLOSED", "ucm_error": str(exc)}
    net_pnl = outcome.net_pnl
    total_cost = outcome.total_cost_amt
    cost_bps = outcome.total_round_trip_bps

    state["cash"] = float(state.get("cash", 0.0)) + cost_basis + net_pnl
    state["realized_pnl"] = float(state.get("realized_pnl", 0.0)) + net_pnl

    closed = {
        **position,
        "closed_at": utc_now(),
        "closed_bar": bar_time,
        "exit_price": exit_price,
        "exit_fee": total_cost,
        "realized_pnl": net_pnl,
        "return_pct": (exit_price - entry_price) / entry_price * 100.0 if entry_price else 0.0,
        "net_return_pct": net_pnl / cost_basis * 100.0 if cost_basis > 0 else 0.0,
        "cost_bps_applied": cost_bps,
        "close_reason": reason,
    }
    state.setdefault("closed_trades", []).append(closed)
    state["position"] = None
    _emit(
        settings,
        "CLEAN_POSITION_CLOSED",
        position=closed,
        trade_uid=str(position.get("position_id", "")),
        candle_uid=bar_time,
        signal_price=float(position.get("signal_price", entry_price)),
        fill_price=exit_price,
        fee=round(outcome.fee_entry_amt + outcome.fee_exit_amt, 8),
        slippage=round(outcome.slippage_amt, 8),
        qty=qty,
        notional=round(qty * exit_price, 8),
        entry_reason=str(position.get("signal_reason", "")),
        exit_reason=reason,
        regime=position.get("metadata", {}).get("regime") if isinstance(position.get("metadata"), dict) else None,
        timeframe=settings.timeframe,
    )
    _send_telegram(
        settings,
        f"CLEAN PAPER CLOSED {settings.symbol} {reason} exit={exit_price:.6f} pnl={net_pnl:+.2f}",
    )
    return closed


def _try_close(
    settings: CleanPaperSettings,
    state: dict[str, Any],
    exit_price: float,
    reason: str,
    bar_time: str,
) -> str:
    """Attempt position close. Returns 'CLOSE' on success, 'UCM_ERROR' if UCM raised.

    If UCM raises, state/cash/position are NOT modified (fail-closed guarantee).
    """
    result = _close_position(settings, state, exit_price, reason, bar_time)
    if isinstance(result, dict) and result.get("action") == "UCM_FAIL_CLOSED":
        return "UCM_ERROR"
    return "CLOSE"


def _create_pending_order(
    settings: CleanPaperSettings,
    state: dict[str, Any],
    signal: Signal,
    signal_row: pd.Series,
    signal_bar_time: str,
) -> dict[str, Any] | None:
    """Record a pending execution intent. Fill happens in the NEXT run_cycle call only.

    Clean paper is long-only. SELL signals are explicitly rejected with a logged event.
    Never fills in the same cycle — causal guarantee.
    """
    if signal.side != "BUY":
        _emit(settings, "CLEAN_SELL_REJECTED",
              side=signal.side,
              strategy=signal.strategy,
              reason=signal.reason,
              bar_time=signal_bar_time)
        return None
    if state.get("position") is not None or state.get("pending_order") is not None:
        return None
    pending: dict[str, Any] = {
        "signal_price": float(signal_row["Close"]),
        "signal_bar": signal_bar_time,
        "stop_price": float(signal.stop_price),
        "take_profit": float(signal.take_profit),
        "strategy": signal.strategy,
        "reason": signal.reason,
        "metadata": dict(signal.metadata),
        "created_at": utc_now(),
    }
    state["pending_order"] = pending
    return pending


def _fill_pending_order(
    settings: CleanPaperSettings,
    state: dict[str, Any],
    fill_price: float,
    fill_bar_time: str,
    atr_pct_val: float,
) -> dict[str, Any] | None:
    """Fill the pending order at fill_price (first price observed after signal bar)."""
    pending = state.get("pending_order")
    if not isinstance(pending, dict):
        return None
    if state.get("position") is not None:
        state.pop("pending_order", None)
        return None

    stop_price = float(pending["stop_price"])
    take_profit = float(pending["take_profit"])
    # Entry-gap validation — single policy via validate_entry_price() shared with backtest.
    # All pending orders are BUY (SELL is rejected at _create_pending_order).
    _entry_stub = Signal(
        strategy=str(pending.get("strategy", "")),
        side="BUY",
        score=0.0,
        reason="",
        stop_price=stop_price,
        take_profit=take_profit,
        metadata={},
    )
    _entry_valid, _entry_reason = validate_entry_price(fill_price, _entry_stub)
    if not _entry_valid:
        _emit(settings, "CLEAN_PENDING_DISCARDED",
              reason=_entry_reason,
              fill_price=fill_price, stop_price=stop_price, take_profit=take_profit)
        state.pop("pending_order", None)
        return None

    risk_per_unit = fill_price - stop_price  # BUY only: always > 0 after guard above
    cash = float(state.get("cash", settings.balance))
    equity_now = _equity(state, fill_price)
    risk_qty = (equity_now * settings.risk_per_trade_pct) / risk_per_unit
    # Cash qty: no entry fee at open; UCM settles all costs at close
    cash_qty = cash / fill_price if fill_price > 0 else 0.0
    qty = max(0.0, min(risk_qty, cash_qty))
    if qty <= 0:
        state.pop("pending_order", None)
        return None

    cost_basis = qty * fill_price
    if cost_basis > cash:
        state.pop("pending_order", None)
        return None

    state["cash"] = cash - cost_basis
    state.pop("pending_order", None)

    position: dict[str, Any] = {
        "position_id": "clean_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "symbol": settings.symbol,
        "side": "BUY",
        "opened_at": utc_now(),
        "opened_bar": fill_bar_time,
        "strategy": pending.get("strategy", "unknown"),
        "qty": qty,
        "entry_price": fill_price,
        "signal_price": float(pending.get("signal_price", fill_price)),
        "signal_bar": pending.get("signal_bar", ""),
        "entry_fee": 0.0,   # all costs settled by UnifiedCostModel at close
        "cost_basis": cost_basis,
        "stop_loss": stop_price,
        "stop_price_at_entry": stop_price,  # preserved for UCM R-calc at close
        "take_profit": float(pending["take_profit"]),
        "trail_atr_mult": float(pending.get("metadata", {}).get("trail_atr_mult", 10.0)),
        "signal_reason": pending.get("reason", ""),
        "metadata": pending.get("metadata", {}),
        "atr_pct_at_entry": atr_pct_val,
    }
    state["position"] = position
    return position


def run_cycle(settings: CleanPaperSettings) -> dict[str, Any]:
    state = _read_state(settings)

    # Fail-closed: corrupt state blocks all trade actions — no balance reset, no position loss,
    # no new orders, no _write_state call (file untouched).
    if state.get("_corrupt_recovery"):
        report: dict[str, Any] = {
            "action": "STATE_CORRUPT_BLOCKED",
            "symbol": settings.symbol,
            "corrupt_error": state.get("_corrupt_error", ""),
        }
        _emit(settings, "CLEAN_STATE_CORRUPT_BLOCKED",
              error=state.get("_corrupt_error", ""),
              symbol=settings.symbol)
        return report

    df, source = _prepared_frame(settings)

    # Signal bar: df[-2] (closed bar used for strategy evaluation)
    signal, signal_row = _signal(settings, df)
    signal_bar_time = str(pd.to_datetime(signal_row["datetime"], utc=True))

    # Current bar: df[-1] (most recently closed bar, used for fills and position management)
    current_row = df.iloc[-1]
    current_bar_time = str(pd.to_datetime(current_row["datetime"], utc=True))
    last = float(current_row["Close"])

    # --- Stale / duplicate check ---
    previous_bar = str(state.get("last_processed_bar") or "")
    if previous_bar:
        try:
            stale_or_duplicate = (
                pd.to_datetime(signal_bar_time, utc=True) <= pd.to_datetime(previous_bar, utc=True)
            )
        except Exception:
            stale_or_duplicate = previous_bar == signal_bar_time
    else:
        stale_or_duplicate = False

    if stale_or_duplicate:
        report = {
            "action": "SKIP_STALE_OR_DUPLICATE_BAR",
            "symbol": settings.symbol,
            "bar_time": signal_bar_time,
            "previous_bar": previous_bar,
            "source": source,
            "last": last,
            "equity": _equity(state, last),
            "cash": float(state.get("cash", 0.0)),
            "position_open": isinstance(state.get("position"), dict),
        }
        _emit(settings, "CLEAN_CYCLE_SKIPPED", **report)
        return report

    state["last_processed_bar"] = signal_bar_time
    action = "HOLD"

    # --- STEP 1: Fill any pending order ---
    pending = state.get("pending_order")
    if isinstance(pending, dict) and state.get("position") is None:
        pending_bar = str(pending.get("signal_bar", ""))
        try:
            has_next_bar = (
                pd.to_datetime(current_bar_time, utc=True) > pd.to_datetime(pending_bar, utc=True)
            )
        except Exception:
            has_next_bar = current_bar_time != pending_bar
        if has_next_bar:
            fill_price = float(current_row["Open"])
            atr_fill = _atr_pct_from_row(current_row)
            filled = _fill_pending_order(settings, state, fill_price, current_bar_time, atr_fill)
            if filled:
                action = "FILL_PENDING"
                _emit(
                    settings,
                    "CLEAN_POSITION_OPENED",
                    position=filled,
                    trade_uid=str(filled.get("position_id", "")),
                    candle_uid=current_bar_time,
                    signal_price=float(pending.get("signal_price", fill_price)),
                    fill_price=fill_price,
                    fee=0.0,
                    slippage=0.0,
                    qty=float(filled.get("qty", 0.0)),
                    notional=round(float(filled.get("qty", 0.0)) * fill_price, 8),
                    entry_reason=str(pending.get("reason", "")),
                    exit_reason=None,
                    regime=pending.get("metadata", {}).get("regime") if isinstance(pending.get("metadata"), dict) else None,
                    timeframe=settings.timeframe,
                )
                _send_telegram(
                    settings,
                    f"CLEAN PAPER OPEN {settings.symbol} BUY fill={fill_price:.6f} "
                    f"stop={float(pending['stop_price']):.6f} qty={filled['qty']:.4f}",
                )

    # --- STEP 2: Position management using current bar OHLC ---
    open_p = float(current_row["Open"])
    high = float(current_row["High"])
    low = float(current_row["Low"])
    atr_val = float(current_row["atr14"]) if "atr14" in current_row.index else 0.0

    position = state.get("position")
    if isinstance(position, dict):
        stop = float(position["stop_loss"])
        tp = float(position.get("take_profit", float("inf")))
        side = str(position.get("side", "BUY")).upper()

        if side == "BUY":
            if open_p <= stop:                          # gap down through SL
                action = _try_close(settings, state, min(open_p, stop), "SL_GAP", current_bar_time)
            elif open_p >= tp:                          # gap up through TP (conservative: fill at TP)
                action = _try_close(settings, state, tp, "TP_GAP", current_bar_time)
            elif low <= stop and high >= tp:            # both hit same bar: SL wins
                action = _try_close(settings, state, stop, "SL_SAME_BAR", current_bar_time)
            elif low <= stop:                           # normal SL
                action = _try_close(settings, state, stop, "SL", current_bar_time)
            elif high >= tp:                            # normal TP
                action = _try_close(settings, state, tp, "TP", current_bar_time)
            else:
                new_stop = max(stop, last - atr_val * float(position.get("trail_atr_mult", 10.0)))
                if new_stop > stop:
                    position["stop_loss"] = new_stop
                    action = "TRAIL_UPDATE"
                    _emit(
                        settings, "CLEAN_TRAIL_UPDATED",
                        symbol=settings.symbol, old_stop=stop, new_stop=new_stop,
                        bar_time=current_bar_time,
                    )

    # --- STEP 3: New signal → create pending order (NEVER fill in same cycle) ---
    # Causal guarantee: the pending is persisted via _write_state before it can be filled.
    # Fill happens exclusively in STEP 1 of a subsequent run_cycle call, using that
    # cycle's current_row["Open"] — a price observed AFTER this state was written.
    if state.get("position") is None and state.get("pending_order") is None and signal is not None:
        pending_new = _create_pending_order(settings, state, signal, signal_row, signal_bar_time)
        if pending_new is not None:
            action = "PENDING_ORDER_CREATED"
        elif signal.side != "BUY":
            action = "SELL_REJECTED"

    _write_state(settings, state)
    report = {
        "action": action,
        "symbol": settings.symbol,
        "bar_time": signal_bar_time,
        "source": source,
        "last": last,
        "equity": _equity(state, last),
        "cash": float(state.get("cash", 0.0)),
        "position_open": isinstance(state.get("position"), dict),
        "signal": asdict(signal) if signal is not None else None,
    }
    _emit(settings, "CLEAN_CYCLE_COMPLETED", **report)
    return report


def format_cycle(report: dict[str, Any]) -> str:
    signal = report.get("signal") or {}
    reason = signal.get("reason", "no_signal") if isinstance(signal, dict) else "no_signal"
    previous = str(report.get("previous_bar") or "")
    previous_text = f" previous_bar={previous}" if previous else ""
    return (
        "CLEAN PAPER CYCLE\n"
        f"symbol={report['symbol']} action={report['action']} source={report['source']} "
        f"bar={report['bar_time']}{previous_text}\n"
        f"last={float(report.get('last', 0.0)):.6f} equity={float(report.get('equity', 0.0)):.2f} "
        f"cash={float(report.get('cash', 0.0)):.2f} "
        f"position_open={'YES' if report.get('position_open') else 'NO'}\n"
        f"signal_reason={reason}"
    )


def send_telegram_cycle(settings: CleanPaperSettings, report: dict[str, Any]) -> dict[str, Any]:
    return _send_telegram(settings, format_cycle(report))


def _notify_cycle(settings: CleanPaperSettings, report: dict[str, Any]) -> None:
    if settings.telegram_notify_every_cycle:
        send_telegram_cycle(settings, report)


def run_loop(settings: CleanPaperSettings) -> None:
    cycles = 0
    start_result = _send_telegram(
        settings,
        f"CLEAN PAPER STARTED {settings.symbol} {settings.timeframe} profile={settings.profile} "
        f"market_data={settings.market_data_mode} notify_every_cycle={settings.telegram_notify_every_cycle}",
    )
    if settings.telegram_enabled:
        print(
            f"TELEGRAM_START ok={start_result.get('ok')} reason={start_result.get('reason', '')} "
            f"status={start_result.get('status', '')}",
            flush=True,
        )
        if not settings.telegram_notify_every_cycle:
            print(
                "TELEGRAM_CYCLE notify=OFF add --telegram-every-cycle to receive HOLD/SKIP cycle summaries",
                flush=True,
            )
    while True:
        report = run_cycle(settings)
        print(format_cycle(report), flush=True)
        _notify_cycle(settings, report)
        cycles += 1
        if settings.max_cycles and cycles >= settings.max_cycles:
            return
        time.sleep(max(1.0, settings.poll_seconds))
