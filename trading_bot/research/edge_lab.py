"""STRAT-02/03 edge research engine.

Pipeline
--------
1. Load STRAT-01 cached parquet (15m signal frame, 5m execution frame).
2. Hard fail-closed guard: phases 2/3 can never see candles at or after
   the locked ``oos_start`` boundary.
3. Vectorised signal masks (per hypothesis family) on closed 15m candles.
4. Causal execution: a signal fired at the close of 15m bar *t* is filled
   at the open of the first 5m candle whose open_time equals that close
   time. Exits are simulated on 5m candles with the exact clean_bot gap
   policy (SL worst-case on same bar, gap fills through SL, conservative
   TP on favourable gaps).
5. Sizing-free TradeEvents are produced first; a portfolio replay then
   applies fixed 0.5% equity risk per trade, qty cash cap and
   UnifiedCostModel costs for any scenario. This keeps conservative /
   severe scenario re-runs exact (costs change equity compounding).
6. Every evaluated configuration is appended to a persistent trial log.

Diagnostic-only. No orders, no exchange access, no credentials.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from trading_bot.clean_bot.indicators import add_indicators
from trading_bot.clean_bot.models import Signal, validate_entry_price
from trading_bot.core.unified_trade_cost import UnifiedCostModel

# ---------------------------------------------------------------------------
# Constants / safety guards
# ---------------------------------------------------------------------------

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False
LIVE_TRADING_ALLOWED = False

RISK_PER_TRADE = 0.005          # fixed 0.5% of equity — the ONLY allowed value
STARTING_EQUITY = 1000.0
EXEC_TIMEFRAME = "5m"           # costs are charged at the execution timeframe
ASSETS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT")
SYMBOL_MAP = {a: f"{a[:-4]}/USDT" for a in ASSETS}

DEFAULT_CACHE_DIR = Path("data/strat01_cache")
DEFAULT_RESEARCH_DIR = Path("data/edge_research")
TRIAL_LOG_NAME = "trial_log.jsonl"
SPLIT_LOCK_NAME = "strat01_temporal_splits.json"

BARS_15M_PER_DAY = 96
BARS_5M_PER_DAY = 288


# ---------------------------------------------------------------------------
# Split contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SplitContract:
    input_hash: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    lock_sha256: str

    @staticmethod
    def load(cache_dir: Path = DEFAULT_CACHE_DIR) -> "SplitContract":
        lock_path = Path(cache_dir) / SPLIT_LOCK_NAME
        if not lock_path.exists():
            raise FileNotFoundError(
                f"Split lock file missing: {lock_path}. Run STRAT-01 first."
            )
        raw_bytes = lock_path.read_bytes()
        d = json.loads(raw_bytes.decode("utf-8"))
        return SplitContract(
            input_hash=d["input_hash"],
            train_start=pd.Timestamp(d["train_start"]),
            train_end=pd.Timestamp(d["train_end"]),
            val_start=pd.Timestamp(d["val_start"]),
            val_end=pd.Timestamp(d["val_end"]),
            oos_start=pd.Timestamp(d["oos_start"]),
            oos_end=pd.Timestamp(d["oos_end"]),
            lock_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )

    def window(self, split: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
        if split == "train":
            return self.train_start, self.train_end
        if split == "validation":
            return self.val_start, self.val_end
        if split == "train_val":
            return self.train_start, self.val_end
        if split == "final_oos":
            return self.oos_start, self.oos_end
        raise ValueError(f"Unknown split '{split}'")


class OOSContaminationError(RuntimeError):
    """Raised when phases 2/3 attempt to touch final-OOS candles."""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_EXTRA_PRIOR_WINDOWS = (96, 192)
_XS_FORMATION_BARS = {3: 3 * BARS_15M_PER_DAY, 7: 7 * BARS_15M_PER_DAY, 14: 14 * BARS_15M_PER_DAY}


def _to_clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "datetime": pd.to_datetime(df["open_time_utc"], utc=True),
            "Open": df["open"].astype(float),
            "High": df["high"].astype(float),
            "Low": df["low"].astype(float),
            "Close": df["close"].astype(float),
            "Volume": df["volume"].astype(float),
        }
    )
    return out.sort_values("datetime").reset_index(drop=True)


def _add_research_indicators(df15: pd.DataFrame) -> pd.DataFrame:
    out = add_indicators(df15)
    high, low, close = out["High"], out["Low"], out["Close"]
    for n in _EXTRA_PRIOR_WINDOWS:
        out[f"prior_high_{n}"] = high.shift(1).rolling(n).max()
        out[f"prior_low_{n}"] = low.shift(1).rolling(n).min()
    # Volatility-compression rank: percentile of current atr_pct inside the
    # trailing 96-bar (1-day) distribution. Causal (uses bar t and earlier).
    out["atr_pct_rank_96"] = out["atr_pct"].rolling(96).rank(pct=True)
    for days, bars in _XS_FORMATION_BARS.items():
        out[f"ret_{days}d"] = close / close.shift(bars) - 1.0
    return out


def load_asset_frames(
    asset: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load full-history 15m (with indicators) and 5m (with ATR) frames."""
    cache_dir = Path(cache_dir)
    p15 = cache_dir / f"{asset}_15m.parquet"
    p5 = cache_dir / f"{asset}_5m.parquet"
    for p in (p15, p5):
        if not p.exists():
            raise FileNotFoundError(f"Missing STRAT-01 cache file: {p}")

    df15 = _add_research_indicators(_to_clean_columns(pd.read_parquet(p15)))

    df5 = _to_clean_columns(pd.read_parquet(p5))
    prev_close = df5["Close"].shift(1)
    tr = pd.concat(
        [
            (df5["High"] - df5["Low"]).abs(),
            (df5["High"] - prev_close).abs(),
            (df5["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df5["atr14"] = tr.rolling(14).mean()
    df5["atr_pct"] = df5["atr14"] / df5["Close"].replace(0, pd.NA) * 100.0
    return df15, df5


def guard_no_oos(df: pd.DataFrame, contract: SplitContract, phase: str) -> pd.DataFrame:
    """Drop every candle at or after oos_start. Phases 2/3 MUST use this."""
    mask = df["datetime"] < contract.oos_start
    dropped = int((~mask).sum())
    out = df.loc[mask].reset_index(drop=True)
    if (out["datetime"] >= contract.oos_start).any():
        raise OOSContaminationError(f"[{phase}] OOS candles survived the guard")
    out.attrs["oos_rows_dropped"] = dropped
    return out


# ---------------------------------------------------------------------------
# Trade events (sizing-free)
# ---------------------------------------------------------------------------

@dataclass
class TradeEvent:
    """A fully resolved trade without position sizing or costs."""

    family: str
    config_id: str
    asset: str
    side: str                  # BUY / SELL
    signal_time: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    stop_price: float
    exit_reason: str
    bars_held_5m: int
    atr_pct_entry: float       # 5m atr_pct at entry bar (cost model input)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Causal 15m -> 5m execution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DirectionalSignalSpec:
    """One directional signal extracted from the 15m frame."""

    idx15: int
    side: str
    stop_atr_mult: float
    exit_style: str            # "fixed_rr" | "atr_trailing" | "time_stop"
    rr: float = 0.0            # for fixed_rr
    trail_atr_mult: float = 0.0
    max_hold_bars_5m: int = 0


class CausalExecutor:
    """Simulates execution of 15m signals on the 5m frame.

    Entry: open of the first 5m bar whose open time >= 15m bar close time.
    Exit : exact clean_bot gap policy, evaluated on 5m candles.
    """

    def __init__(self, df15: pd.DataFrame, df5: pd.DataFrame) -> None:
        self.df15 = df15
        self.df5 = df5
        self.t15_close = (
            df15["datetime"] + pd.Timedelta(minutes=15)
        ).to_numpy(dtype="datetime64[ns]")
        self.t5_open = df5["datetime"].to_numpy(dtype="datetime64[ns]")
        self.o5 = df5["Open"].to_numpy(dtype=float)
        self.h5 = df5["High"].to_numpy(dtype=float)
        self.l5 = df5["Low"].to_numpy(dtype=float)
        self.c5 = df5["Close"].to_numpy(dtype=float)
        self.atrpct5 = df5["atr_pct"].to_numpy(dtype=float)
        self.atr15 = df15["atr14"].to_numpy(dtype=float)
        # 15m index of the latest CLOSED 15m bar for each 5m bar (causal map
        # used by trailing exits: a 15m value becomes visible only after the
        # 15m bar has closed).
        self.last_closed_15_for_5 = (
            np.searchsorted(self.t15_close, self.t5_open, side="right") - 1
        )

    def entry_bar_for_signal(self, idx15: int) -> Optional[int]:
        target = self.t15_close[idx15]
        j = int(np.searchsorted(self.t5_open, target, side="left"))
        if j >= len(self.t5_open):
            return None
        return j

    # -- exits ------------------------------------------------------------

    def _exit_fixed_rr(
        self, side: str, entry_idx5: int, entry: float, stop: float, tp: float, end: int
    ) -> Tuple[int, float, str]:
        o, h, l = self.o5, self.h5, self.l5
        for j in range(entry_idx5, end + 1):
            if side == "BUY":
                if o[j] <= stop:
                    return j, min(o[j], stop), "SL_GAP"
                if o[j] >= tp:
                    return j, tp, "TP_GAP"
                hit_sl = l[j] <= stop
                hit_tp = h[j] >= tp
                if hit_sl and hit_tp:
                    return j, stop, "SL_SAME_BAR"
                if hit_sl:
                    return j, stop, "SL"
                if hit_tp:
                    return j, tp, "TP"
            else:
                if o[j] >= stop:
                    return j, max(o[j], stop), "SL_GAP"
                if o[j] <= tp:
                    return j, tp, "TP_GAP"
                hit_sl = h[j] >= stop
                hit_tp = l[j] <= tp
                if hit_sl and hit_tp:
                    return j, stop, "SL_SAME_BAR"
                if hit_sl:
                    return j, stop, "SL"
                if hit_tp:
                    return j, tp, "TP"
        return end, float(self.c5[end]), "TIME_EXIT"

    def _exit_trailing(
        self,
        side: str,
        entry_idx5: int,
        stop: float,
        trail_mult: float,
        end: int,
    ) -> Tuple[int, float, str]:
        o, h, l, c = self.o5, self.h5, self.l5, self.c5
        trailing = stop
        for j in range(entry_idx5, end + 1):
            if side == "BUY":
                if o[j] <= trailing:
                    return j, min(o[j], trailing), "TRAIL_GAP"
                if l[j] <= trailing:
                    return j, trailing, "TRAIL"
            else:
                if o[j] >= trailing:
                    return j, max(o[j], trailing), "TRAIL_GAP"
                if h[j] >= trailing:
                    return j, trailing, "TRAIL"
            k15 = self.last_closed_15_for_5[j]
            atr = self.atr15[k15] if k15 >= 0 else float("nan")
            if atr and atr > 0 and not math.isnan(atr):
                if side == "BUY":
                    trailing = max(trailing, c[j] - atr * trail_mult)
                else:
                    trailing = min(trailing, c[j] + atr * trail_mult)
        return end, float(c[end]), "TIME_EXIT"

    def _exit_time_stop(
        self, side: str, entry_idx5: int, stop: float, end: int
    ) -> Tuple[int, float, str]:
        o, h, l = self.o5, self.h5, self.l5
        for j in range(entry_idx5, end + 1):
            if side == "BUY":
                if o[j] <= stop:
                    return j, min(o[j], stop), "SL_GAP"
                if l[j] <= stop:
                    return j, stop, "SL"
            else:
                if o[j] >= stop:
                    return j, max(o[j], stop), "SL_GAP"
                if h[j] >= stop:
                    return j, stop, "SL"
        return end, float(self.c5[end]), "TIME_EXIT"

    # -- main loop ---------------------------------------------------------

    def run(
        self,
        specs: Sequence[DirectionalSignalSpec],
        *,
        family: str,
        config_id: str,
        asset: str,
        window_start: pd.Timestamp,
        window_end: pd.Timestamp,
    ) -> List[TradeEvent]:
        """Execute signal specs causally; one position per asset at a time."""
        events: List[TradeEvent] = []
        t15 = self.df15["datetime"].to_numpy(dtype="datetime64[ns]")
        ws = np.datetime64(window_start.tz_convert("UTC").tz_localize(None))
        we = np.datetime64(window_end.tz_convert("UTC").tz_localize(None))
        busy_until = -1  # 5m index until which the asset slot is occupied

        for spec in sorted(specs, key=lambda s: s.idx15):
            st = t15[spec.idx15]
            if st < ws or st >= we:
                continue
            j = self.entry_bar_for_signal(spec.idx15)
            if j is None or j >= len(self.o5) - 1:
                continue
            if j <= busy_until:
                continue
            row15 = self.df15.iloc[spec.idx15]
            atr = float(row15["atr14"])
            if not (atr > 0):
                continue
            entry = float(self.o5[j])
            if spec.side == "BUY":
                stop = entry - atr * spec.stop_atr_mult
                tp = entry + atr * spec.stop_atr_mult * spec.rr if spec.exit_style == "fixed_rr" else 0.0
            else:
                stop = entry + atr * spec.stop_atr_mult
                tp = entry - atr * spec.stop_atr_mult * spec.rr if spec.exit_style == "fixed_rr" else 0.0
            if stop <= 0 or entry <= 0:
                continue
            sig = Signal(family, spec.side, 0.0, config_id, stop, tp, {})
            ok, _reason = validate_entry_price(entry, sig)
            if not ok:
                continue

            # Trades may run past the window end candle-wise, but never into
            # the OOS guard (the frames themselves are truncated upstream).
            end = min(len(self.o5) - 1, j + max(1, spec.max_hold_bars_5m))
            if spec.exit_style == "fixed_rr":
                xj, xp, xr = self._exit_fixed_rr(spec.side, j, entry, stop, tp, end)
            elif spec.exit_style == "atr_trailing":
                xj, xp, xr = self._exit_trailing(spec.side, j, stop, spec.trail_atr_mult, end)
            elif spec.exit_style == "time_stop":
                xj, xp, xr = self._exit_time_stop(spec.side, j, stop, end)
            else:
                raise ValueError(f"unknown exit_style {spec.exit_style}")
            if xp <= 0:
                continue

            apct = float(self.atrpct5[j])
            if math.isnan(apct) or apct < 0:
                apct = 0.0
            events.append(
                TradeEvent(
                    family=family,
                    config_id=config_id,
                    asset=asset,
                    side=spec.side,
                    signal_time=str(pd.Timestamp(st, tz="UTC")),
                    entry_time=str(self.df5.iloc[j]["datetime"]),
                    exit_time=str(self.df5.iloc[xj]["datetime"]),
                    entry_price=entry,
                    exit_price=float(xp),
                    stop_price=float(stop),
                    exit_reason=xr,
                    bars_held_5m=int(xj - j),
                    atr_pct_entry=apct,
                )
            )
            busy_until = xj
        return events


# ---------------------------------------------------------------------------
# Portfolio replay with costs (scenario-exact)
# ---------------------------------------------------------------------------

@dataclass
class ReplayedTrade:
    event: TradeEvent
    qty: float
    gross_pnl: float
    cost: float
    net_pnl: float
    net_R: float
    gross_R: float
    cost_R: float
    equity_after: float


def portfolio_replay(
    events: Iterable[TradeEvent],
    *,
    scenario: str,
    starting_equity: float = STARTING_EQUITY,
    risk_per_trade: float = RISK_PER_TRADE,
) -> List[ReplayedTrade]:
    """Chronological replay with shared equity, 0.5% fixed risk and costs.

    Equity is committed at entry time and settled at exit time, so
    overlapping trades across assets are sized with the equity available
    when each of them was opened (no look-ahead on PnL).
    """
    if abs(risk_per_trade - RISK_PER_TRADE) > 1e-12:
        raise ValueError("risk_per_trade is fixed at 0.005 for this research")

    evs = sorted(events, key=lambda e: (e.entry_time, e.exit_time, e.asset))
    # Settlement queue: (exit_time, net_pnl) applied before each later entry.
    pending: List[Tuple[str, float]] = []
    equity = starting_equity
    out: List[ReplayedTrade] = []

    for ev in evs:
        # settle every trade that exited before this entry
        still: List[Tuple[str, float]] = []
        for xt, pnl in pending:
            if xt <= ev.entry_time:
                equity += pnl
            else:
                still.append((xt, pnl))
        pending = still

        risk_unit = abs(ev.entry_price - ev.stop_price)
        if risk_unit <= 0 or equity <= 0:
            continue
        qty_by_risk = (equity * risk_per_trade) / risk_unit
        qty_by_cash = equity / ev.entry_price
        qty = max(0.0, min(qty_by_risk, qty_by_cash))
        if qty <= 0:
            continue

        direction = 1.0 if ev.side == "BUY" else -1.0
        gross = (ev.exit_price - ev.entry_price) * qty * direction
        initial_risk = max(1e-12, qty * risk_unit)
        res = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=gross,
            initial_risk=initial_risk,
            entry_price=ev.entry_price,
            exit_price=ev.exit_price,
            quantity=qty,
            scenario=scenario,
            symbol=SYMBOL_MAP.get(ev.asset, "BTC/USDT"),
            timeframe=EXEC_TIMEFRAME,
            atr_pct=ev.atr_pct_entry,
        )
        pending.append((ev.exit_time, res["net_pnl"]))
        out.append(
            ReplayedTrade(
                event=ev,
                qty=qty,
                gross_pnl=res["gross_pnl"],
                cost=res["cost_amt"],
                net_pnl=res["net_pnl"],
                net_R=res["net_R"],
                gross_R=res["gross_R"],
                cost_R=res["cost_R"],
                equity_after=float("nan"),  # filled below
            )
        )

    # settle the tail and rebuild the equity-after sequence by exit order
    equity = starting_equity
    for tr in sorted(out, key=lambda t: t.event.exit_time):
        equity += tr.net_pnl
        tr.equity_after = equity
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    trades: Sequence[ReplayedTrade],
    *,
    starting_equity: float = STARTING_EQUITY,
    bars_in_window_15m: int = 0,
    n_signals: int = 0,
) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": None,
            "net_pnl": 0.0, "return_pct": 0.0, "max_drawdown_pct": 0.0,
            "avg_net_R": 0.0, "sum_net_R": 0.0, "sharpe_per_trade": None,
            "total_costs": 0.0, "gross_pnl_sum": 0.0,
            "cost_to_gross_profit": None, "signal_density_per_1k_bars": 0.0,
            "turnover_trades_per_day": 0.0, "avg_hold_hours": 0.0,
            "skew_net_R": None, "kurtosis_net_R": None,
            "top3_profit_share": None,
        }

    ordered = sorted(trades, key=lambda t: t.event.exit_time)
    pnls = np.array([t.net_pnl for t in ordered], dtype=float)
    rs = np.array([t.net_R for t in ordered], dtype=float)
    costs = np.array([t.cost for t in ordered], dtype=float)
    grosses = np.array([t.gross_pnl for t in ordered], dtype=float)

    equity = starting_equity + np.cumsum(pnls)
    peak = np.maximum.accumulate(np.concatenate([[starting_equity], equity]))[1:]
    dd = np.where(peak > 0, (peak - equity) / peak * 100.0, 0.0)

    gp = float(pnls[pnls > 0].sum())
    gl = float(-pnls[pnls < 0].sum())
    wins = int((pnls > 0).sum())
    losses = int((pnls < 0).sum())

    mean_r = float(rs.mean())
    std_r = float(rs.std(ddof=1)) if n > 1 else 0.0
    sharpe = mean_r / std_r if std_r > 0 else None

    t0 = pd.Timestamp(ordered[0].event.entry_time)
    t1 = pd.Timestamp(ordered[-1].event.exit_time)
    span_days = max((t1 - t0).total_seconds() / 86400.0, 1e-9)
    hold_hours = float(np.mean([t.event.bars_held_5m for t in ordered]) * 5.0 / 60.0)

    pos = pnls[pnls > 0]
    top3_share = (
        float(np.sort(pos)[-3:].sum() / pos.sum()) if pos.size > 0 else None
    )

    def _skew_kurt(x: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
        if x.size < 3 or x.std(ddof=0) == 0:
            return None, None
        z = (x - x.mean()) / x.std(ddof=0)
        return float((z ** 3).mean()), float((z ** 4).mean())

    skew, kurt = _skew_kurt(rs)

    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins / n * 100.0,
        "gross_profit": gp,
        "gross_loss": gl,
        "profit_factor": (gp / gl) if gl > 0 else None,
        "net_pnl": float(pnls.sum()),
        "return_pct": float(pnls.sum()) / starting_equity * 100.0,
        "max_drawdown_pct": float(dd.max()) if dd.size else 0.0,
        "avg_net_R": mean_r,
        "sum_net_R": float(rs.sum()),
        "sharpe_per_trade": sharpe,
        "total_costs": float(costs.sum()),
        "gross_pnl_sum": float(grosses.sum()),
        "cost_to_gross_profit": (
            float(costs.sum() / grosses[grosses > 0].sum())
            if (grosses > 0).any()
            else None
        ),
        "signal_density_per_1k_bars": (
            n_signals / bars_in_window_15m * 1000.0 if bars_in_window_15m else 0.0
        ),
        "turnover_trades_per_day": n / span_days,
        "avg_hold_hours": hold_hours,
        "skew_net_R": skew,
        "kurtosis_net_R": kurt,
        "top3_profit_share": top3_share,
    }


# ---------------------------------------------------------------------------
# Trial log (append-only, atomic-ish)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def config_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def append_trial(
    research_dir: Path,
    record: Dict[str, Any],
) -> None:
    research_dir = Path(research_dir)
    research_dir.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("logged_at", _utc_now())
    line = json.dumps(record, sort_keys=True, default=str)
    with (research_dir / TRIAL_LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_trial_log(research_dir: Path = DEFAULT_RESEARCH_DIR) -> List[Dict[str, Any]]:
    p = Path(research_dir) / TRIAL_LOG_NAME
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_json_atomic(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp.json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
