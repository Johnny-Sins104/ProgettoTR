"""
core/metrics.py — Institutional-Grade Metrics Engine
======================================================
Provides a comprehensive, production-quality evaluation suite for a crypto
futures ML trading system, covering:

  1. FINANCIAL METRICS (portfolio theory framework)
     - Sharpe / Sortino / Calmar ratios
     - Maximum drawdown, drawdown duration
     - Profit factor, expectancy, gain-to-pain ratio
     - Rolling volatility & rolling return windows

  2. ML QUALITY METRICS  (model calibration framework)
     - ROC-AUC, Precision, Recall, F1-score
     - Brier score, Expected Calibration Error (ECE)

  3. REGIME-SPECIFIC BREAKDOWN
     - Separate statistics per TRENDING / RANGING regime

  4. TEMPORAL DECOMPOSITION
     - Monthly P&L attribution
     - Rolling performance windows (30-day, 90-day)

  5. REPORTING
     - Rich ASCII / tabular console output
     - JSON export (machine-readable)
     - CSV export (spreadsheet-compatible)
     - Matplotlib charts (equity curve, drawdown, calibration)

WHY ACCURACY IS MISLEADING IN TRADING
---------------------------------------
A classifier predicting "always WIN" on a 60 % win-rate dataset yields 60 %
accuracy — yet it never uses a Stop-Loss and will eventually blow the account.
Accuracy ignores:
  (a) the dollar *magnitude* of wins vs losses (reward-to-risk asymmetry),
  (b) the temporal clustering of losses (drawdown path),
  (c) the calibration quality (probability ≠ confidence).

WHY EXPECTANCY MATTERS MORE
------------------------------
Expectancy = E[PnL per trade] = (Win Rate × Avg Win) − (Loss Rate × Avg Loss).
A system with 40 % win rate but 3:1 reward-to-risk has *positive* expectancy and
will grow capital monotonically. A system with 70 % accuracy but 1:3 reward-to-risk
has *negative* expectancy and will ruin. Sharpe ratio adds the volatility dimension,
Sortino isolates downside risk, and Calmar penalises peak drawdown exposure.
"""

from __future__ import annotations

import json
import os
import math
import warnings
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# ── Optional heavy imports ───────────────────────────────────────────────────
try:
    from sklearn.metrics import (
        roc_auc_score, precision_score, recall_score,
        f1_score, brier_score_loss,
    )
    from sklearn.calibration import calibration_curve
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")          # headless rendering — no display needed
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ════════════════════════════════════════════════════════════════════════════
# §1 — DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """
    Minimal, immutable representation of a closed trade.
    All monetary values are expressed in the account base currency (e.g. €).
    """
    pnl: float                        # Net PnL after commission (positive = profit)
    entry_time: Optional[pd.Timestamp] = None
    exit_time:  Optional[pd.Timestamp] = None
    side:       str = "BUY"           # "BUY" | "SELL"
    result:     str = "WIN"           # "WIN" | "WIN_PARTIAL" | "BREAKEVEN" | "LOSS"
    regime:     str = "RANGING"       # "TRENDING" | "RANGING"
    ai_prob:    float = 50.0          # AI predicted win-probability in [0, 100]
    balance_after: float = 0.0        # Equity snapshot after trade close
    conf_comb:  str = ""              # Confluence combination label


@dataclass
class MLPredictionRecord:
    """One ML prediction event (for calibration/AUC analysis)."""
    y_true:  int   # Ground truth label  (1 = win, 0 = loss)
    y_prob:  float # Predicted probability of WIN ∈ [0.0, 1.0]
    regime:  str = "RANGING"


@dataclass
class FinancialMetrics:
    """Scalar financial performance metrics computed from a trade list."""
    # Counts
    total_trades:   int   = 0
    wins:           int   = 0
    losses:         int   = 0
    breakevens:     int   = 0
    partial_wins:   int   = 0

    # Rates
    win_rate:       float = 0.0    # (wins + partial) / total  [0,1]
    loss_rate:      float = 0.0

    # Dollar statistics
    total_pnl:      float = 0.0
    avg_win:        float = 0.0
    avg_loss:       float = 0.0    # magnitude (positive number)
    largest_win:    float = 0.0
    largest_loss:   float = 0.0    # magnitude

    # Risk-adjusted ratios
    expectancy:     float = 0.0    # E[PnL] per trade
    profit_factor:  float = 0.0    # gross_profit / gross_loss
    sharpe:         float = 0.0    # annualised on per-trade returns
    sortino:        float = 0.0    # downside-deviation version
    calmar:         float = 0.0    # CAGR / Max-Drawdown

    # Drawdown
    max_drawdown:   float = 0.0    # peak-to-trough in currency units
    max_dd_pct:     float = 0.0    # in %
    max_dd_duration: int  = 0      # consecutive losing trades at peak DD

    # Volatility
    vol_annualised: float = 0.0    # annualised std of per-trade PnL

    # CAGR proxy (assuming 96 fifteen-minute candles per day)
    cagr_pct:       float = 0.0

    # Gain-to-pain ratio  =  total_pnl / sum(|losses|)
    gain_to_pain:   float = 0.0


@dataclass
class MLMetrics:
    """ML classification quality metrics."""
    roc_auc:     float = 0.0
    precision:   float = 0.0
    recall:      float = 0.0
    f1:          float = 0.0
    brier:       float = 0.0      # lower is better (perfect = 0)
    ece:         float = 0.0      # Expected Calibration Error  (lower is better)
    n_samples:   int   = 0
    # Regime breakdown
    trending_auc:   float = 0.0
    ranging_auc:    float = 0.0


@dataclass
class RegimeMetrics:
    """Financial metrics split by market regime."""
    trending: FinancialMetrics = field(default_factory=FinancialMetrics)
    ranging:  FinancialMetrics = field(default_factory=FinancialMetrics)


@dataclass
class MonthlyBucket:
    """Aggregated monthly performance."""
    month:     str   = ""    # "YYYY-MM"
    pnl:       float = 0.0
    trades:    int   = 0
    win_rate:  float = 0.0
    sharpe:    float = 0.0


@dataclass
class RollingWindow:
    """Performance stats computed over a rolling window."""
    window_label: str   = ""
    sharpe:       float = 0.0
    sortino:      float = 0.0
    vol:          float = 0.0
    pnl:          float = 0.0
    win_rate:     float = 0.0
    n_trades:     int   = 0


@dataclass
class MetricsReport:
    """Top-level container that bundles all computed metrics."""
    financial:  FinancialMetrics    = field(default_factory=FinancialMetrics)
    ml:         MLMetrics           = field(default_factory=MLMetrics)
    regime:     RegimeMetrics       = field(default_factory=RegimeMetrics)
    monthly:    List[MonthlyBucket] = field(default_factory=list)
    rolling:    List[RollingWindow] = field(default_factory=list)
    initial_balance: float          = 1000.0
    final_balance:   float          = 1000.0
    symbol:          str            = "BTC/USDT"
    timeframe:       str            = "15m"


# ════════════════════════════════════════════════════════════════════════════
# §2 — CORE COMPUTATION ENGINE
# ════════════════════════════════════════════════════════════════════════════

# Annualisation factor:  15m bars → 4/h → 96/day → 96*365 per year
_BARS_PER_YEAR_15M = 96 * 365
# "trading days" for annualising per-trade returns (approx 250 trades/yr proxy)
_TRADES_PER_YEAR   = 250


def _safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    """Division with zero-guard."""
    return a / b if abs(b) > 1e-12 else fallback


def _drawdown_series(equity: np.ndarray) -> Tuple[np.ndarray, float, float, int]:
    """
    Compute the full drawdown time-series from an equity curve.

    Returns
    -------
    dd_series     : drawdown at each step (in currency units, always ≤ 0)
    max_dd        : worst drawdown (currency units, positive magnitude)
    max_dd_pct    : worst drawdown as % of peak equity
    max_dd_dur    : length of the longest drawdown sequence (in number of trades)
    """
    if len(equity) == 0:
        return np.array([]), 0.0, 0.0, 0

    running_max   = np.maximum.accumulate(equity)
    dd_series     = equity - running_max           # ≤ 0
    max_dd        = float(-dd_series.min())
    max_dd_pct    = float(_safe_div(-dd_series.min(), running_max[np.argmin(dd_series)]) * 100)

    # Drawdown duration: count consecutive candles below previous peak
    in_dd = (dd_series < 0).astype(int)
    max_dd_dur = 0
    cur = 0
    for v in in_dd:
        if v:
            cur += 1
            max_dd_dur = max(max_dd_dur, cur)
        else:
            cur = 0

    return dd_series, max_dd, max_dd_pct, max_dd_dur


def _sharpe(returns: np.ndarray, periods_per_year: int = _TRADES_PER_YEAR, rf: float = 0.0) -> float:
    """Annualised Sharpe ratio on a series of per-period returns."""
    if len(returns) < 2:
        return 0.0
    excess = returns - rf / periods_per_year
    std    = np.std(excess, ddof=1)
    if std < 1e-12:
        return 0.0
    return float(np.mean(excess) / std * math.sqrt(periods_per_year))


def _sortino(returns: np.ndarray, periods_per_year: int = _TRADES_PER_YEAR, rf: float = 0.0) -> float:
    """
    Annualised Sortino ratio.
    Only penalises downside deviation (returns below the MAR = risk-free rate).
    This is a more realistic risk measure for trading systems since it does NOT
    penalise *upside* volatility (large wins are not treated as risk).
    """
    if len(returns) < 2:
        return 0.0
    mar     = rf / periods_per_year
    neg     = returns[returns < mar] - mar
    if len(neg) == 0:
        return math.inf
    downside_dev = math.sqrt(np.mean(neg ** 2))
    if downside_dev < 1e-12:
        return 0.0
    return float((np.mean(returns) - mar) / downside_dev * math.sqrt(periods_per_year))


def _compute_financial(trades: List[TradeRecord], initial_balance: float) -> FinancialMetrics:
    """Derive all scalar financial metrics from a list of TradeRecord objects."""
    m = FinancialMetrics()
    if not trades:
        return m

    # ── Counts ──────────────────────────────────────────────────────────────
    m.total_trades = len(trades)
    m.wins         = sum(1 for t in trades if t.result == "WIN")
    m.partial_wins = sum(1 for t in trades if t.result == "WIN_PARTIAL")
    m.losses       = sum(1 for t in trades if t.result == "LOSS")
    m.breakevens   = sum(1 for t in trades if t.result == "BREAKEVEN")

    total_wins = m.wins + m.partial_wins
    trade_with_outcome = total_wins + m.losses

    m.win_rate  = _safe_div(total_wins, trade_with_outcome)
    m.loss_rate = _safe_div(m.losses,   trade_with_outcome)

    # ── PnL vectors ─────────────────────────────────────────────────────────
    pnl_arr    = np.array([t.pnl for t in trades], dtype=float)
    gross_wins = pnl_arr[pnl_arr > 0]
    gross_loss = pnl_arr[pnl_arr < 0]

    m.total_pnl    = float(pnl_arr.sum())
    m.avg_win      = float(gross_wins.mean())  if len(gross_wins) else 0.0
    m.avg_loss     = float(-gross_loss.mean()) if len(gross_loss) else 0.0   # magnitude
    m.largest_win  = float(gross_wins.max())   if len(gross_wins) else 0.0
    m.largest_loss = float(-gross_loss.min())  if len(gross_loss) else 0.0

    # ── Expectancy ──────────────────────────────────────────────────────────
    # E[PnL] = (WinRate × AvgWin) − (LossRate × AvgLoss)
    # Positive expectancy → system has edge; accurate regardless of win rate
    m.expectancy   = m.win_rate * m.avg_win - m.loss_rate * m.avg_loss

    # ── Profit factor ───────────────────────────────────────────────────────
    gp = float(gross_wins.sum()) if len(gross_wins) else 0.0
    gl = float(-gross_loss.sum()) if len(gross_loss) else 0.0
    m.profit_factor = _safe_div(gp, gl, fallback=math.inf if gp > 0 else 0.0)

    # ── Gain-to-Pain ────────────────────────────────────────────────────────
    m.gain_to_pain = _safe_div(m.total_pnl, gl)

    # ── Equity curve → drawdown ─────────────────────────────────────────────
    equity = initial_balance + np.cumsum(pnl_arr)
    _, m.max_drawdown, m.max_dd_pct, m.max_dd_dur = _drawdown_series(equity)

    # ── Per-trade returns (normalised by initial balance) ───────────────────
    ret_arr = pnl_arr / initial_balance

    m.sharpe  = _sharpe(ret_arr)
    m.sortino = _sortino(ret_arr)

    # ── Calmar ratio  =  CAGR / MaxDD ───────────────────────────────────────
    # We use a proxy for CAGR based on total PnL over holding period.
    # Proper CAGR requires actual timestamps; here we use a proxy assuming
    # each trade is roughly 1 day apart on average.
    n_years = max(len(trades) / _TRADES_PER_YEAR, 1 / 365)
    final_eq = initial_balance + m.total_pnl
    if final_eq > 0:
        m.cagr_pct = ((final_eq / initial_balance) ** (1 / n_years) - 1) * 100
    m.calmar = _safe_div(m.cagr_pct, m.max_dd_pct)

    # ── Annualised vol ───────────────────────────────────────────────────────
    m.vol_annualised = float(np.std(ret_arr, ddof=1) * math.sqrt(_TRADES_PER_YEAR) * 100)

    return m


def _compute_ml(preds: List[MLPredictionRecord]) -> MLMetrics:
    """
    Compute ML calibration and discrimination metrics.

    ROC-AUC measures the model's ability to *rank* wins above losses — it is
    threshold-independent.  Brier score measures *calibration*: whether the
    stated probability p actually matches the observed win frequency.
    ECE bins predictions and compares predicted probability to empirical
    accuracy within each bin (perfect calibration → ECE = 0).
    """
    m = MLMetrics()
    if not preds or not SKLEARN_AVAILABLE:
        return m

    m.n_samples = len(preds)
    y_true = np.array([p.y_true for p in preds], dtype=int)
    y_prob = np.array([p.y_prob for p in preds], dtype=float)
    y_pred = (y_prob >= 0.5).astype(int)

    try:
        if len(np.unique(y_true)) > 1:
            m.roc_auc   = float(roc_auc_score(y_true, y_prob))
        m.precision = float(precision_score(y_true, y_pred, zero_division=0))
        m.recall    = float(recall_score(y_true, y_pred, zero_division=0))
        m.f1        = float(f1_score(y_true, y_pred, zero_division=0))
        m.brier     = float(brier_score_loss(y_true, y_prob))

        # ── ECE with 10 bins ───────────────────────────────────────────────
        fraction_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=10, strategy="uniform")
        weights = np.histogram(y_prob, bins=10, range=(0, 1))[0]
        weights = weights / (weights.sum() + 1e-12)
        valid_bins = len(fraction_pos)
        m.ece = float(np.sum(np.abs(fraction_pos - mean_pred[:valid_bins]) * weights[:valid_bins]))

    except Exception as exc:
        warnings.warn(f"[Metrics] ML metrics computation failed: {exc}")

    # ── Regime breakdown ────────────────────────────────────────────────────
    for regime_name, attr in [("TRENDING", "trending_auc"), ("RANGING", "ranging_auc")]:
        sub = [p for p in preds if p.regime == regime_name]
        if len(sub) >= 10:
            yt = np.array([p.y_true for p in sub], dtype=int)
            yp = np.array([p.y_prob for p in sub], dtype=float)
            try:
                if len(np.unique(yt)) > 1:
                    setattr(m, attr, float(roc_auc_score(yt, yp)))
            except Exception:
                pass

    return m


def _compute_regime(trades: List[TradeRecord], initial_balance: float) -> RegimeMetrics:
    """Compute financial metrics separately for TRENDING and RANGING regimes."""
    trending = [t for t in trades if t.regime == "TRENDING"]
    ranging  = [t for t in trades if t.regime == "RANGING"]
    return RegimeMetrics(
        trending=_compute_financial(trending, initial_balance),
        ranging =_compute_financial(ranging,  initial_balance),
    )


def _compute_monthly(trades: List[TradeRecord], initial_balance: float) -> List[MonthlyBucket]:
    """
    Bucket trades by calendar month and compute per-month stats.
    Requires trades to have valid entry_time timestamps.
    """
    buckets: Dict[str, List[TradeRecord]] = {}
    for t in trades:
        if t.entry_time is None:
            continue
        key = t.entry_time.strftime("%Y-%m")
        buckets.setdefault(key, []).append(t)

    result = []
    for month in sorted(buckets.keys()):
        group = buckets[month]
        pnl_list = [t.pnl for t in group]
        wins = sum(1 for t in group if t.result in ("WIN", "WIN_PARTIAL"))
        total_with_outcome = sum(1 for t in group if t.result in ("WIN", "WIN_PARTIAL", "LOSS"))

        pnl_arr = np.array(pnl_list, dtype=float)
        ret_arr = pnl_arr / initial_balance

        result.append(MonthlyBucket(
            month=month,
            pnl=float(pnl_arr.sum()),
            trades=len(group),
            win_rate=_safe_div(wins, total_with_outcome),
            sharpe=_sharpe(ret_arr, periods_per_year=max(len(group), 1)),
        ))

    return result


def _compute_rolling(trades: List[TradeRecord], initial_balance: float,
                     window_sizes: Sequence[int] = (30, 90)) -> List[RollingWindow]:
    """
    Compute rolling performance over the last N *trades* for each window size.
    Unlike calendar rolling, this is trade-count-based, which is more relevant
    for systems with variable trade frequency.
    """
    result = []
    for w in window_sizes:
        subset = trades[-w:]
        if not subset:
            continue
        fm = _compute_financial(subset, initial_balance)
        result.append(RollingWindow(
            window_label=f"Last {w} Trades",
            sharpe=fm.sharpe,
            sortino=fm.sortino,
            vol=fm.vol_annualised,
            pnl=fm.total_pnl,
            win_rate=fm.win_rate,
            n_trades=len(subset),
        ))
    return result


# ════════════════════════════════════════════════════════════════════════════
# §3 — PUBLIC API
# ════════════════════════════════════════════════════════════════════════════

class MetricsEngine:
    """
    Stateless, functional metrics engine.
    Accepts raw trade/prediction lists and returns fully populated
    MetricsReport objects — no side effects.

    Usage
    -----
    trades = [TradeRecord(pnl=120.5, result="WIN", regime="TRENDING"), ...]
    preds  = [MLPredictionRecord(y_true=1, y_prob=0.82), ...]
    report = MetricsEngine.compute(trades, preds, initial_balance=1000.0)
    MetricsEngine.print_report(report)
    MetricsEngine.export_json(report, "reports/metrics.json")
    MetricsEngine.export_charts(report, trades, "reports/charts/")
    """

    @staticmethod
    def compute(
        trades:          List[TradeRecord],
        predictions:     Optional[List[MLPredictionRecord]] = None,
        initial_balance: float = 1000.0,
        symbol:          str   = "BTC/USDT",
        timeframe:       str   = "15m",
        rolling_windows: Sequence[int] = (30, 90),
    ) -> MetricsReport:
        """
        Central entry point.  Computes all metrics and returns a MetricsReport.
        
        Parameters
        ----------
        trades          : closed trade records (PnL + metadata)
        predictions     : ML prediction events (y_true, y_prob) — optional
        initial_balance : starting equity
        symbol          : market symbol (for labelling only)
        timeframe       : bar timeframe (for labelling only)
        rolling_windows : sizes in *number of trades* for rolling stats
        """
        final_balance = initial_balance + sum(t.pnl for t in trades) if trades else initial_balance

        report = MetricsReport(
            initial_balance=initial_balance,
            final_balance=final_balance,
            symbol=symbol,
            timeframe=timeframe,
        )
        report.financial = _compute_financial(trades, initial_balance)
        report.ml        = _compute_ml(predictions or [])
        report.regime    = _compute_regime(trades, initial_balance)
        report.monthly   = _compute_monthly(trades, initial_balance)
        report.rolling   = _compute_rolling(trades, initial_balance, rolling_windows)

        return report

    # ── Builders from backtest_lab output ────────────────────────────────────

    @staticmethod
    def from_backtest_output(
        backtest_result:  dict,
        initial_balance:  float = 1000.0,
        ai_models_cache:  Optional[dict] = None,
        symbol:           str = "BTC/USDT",
        timeframe:        str = "15m",
    ) -> MetricsReport:
        """
        Convert the dict returned by `backtest_lab.simulate_backtest` into a
        MetricsReport.  This adapter keeps metrics.py decoupled from the
        backtest engine.

        Parameters
        ----------
        backtest_result  : dict from simulate_backtest() — must contain 'trades' key
        initial_balance  : starting equity
        ai_models_cache  : ai._wf_models dict — used to rebuild MLPredictionRecord list
        """
        raw_trades: List[dict] = backtest_result.get("trades", [])
        trades: List[TradeRecord] = []
        preds:  List[MLPredictionRecord] = []

        for t in raw_trades:
            result_str = t.get("result", "LOSS")
            # Determine win/loss for ML label construction
            y_true = 1 if result_str in ("WIN", "WIN_PARTIAL") else 0
            ai_prob_pct = float(t.get("ai_prob", 50.0))

            trade = TradeRecord(
                pnl=float(t.get("pnl", 0.0)),
                result=result_str,
                side=t.get("side", "BUY"),
                regime=t.get("regime", "RANGING"),
                ai_prob=ai_prob_pct,
                conf_comb=t.get("confluence_comb", ""),
                balance_after=float(t.get("balance", initial_balance)),
            )
            trades.append(trade)

            # Build a prediction record from each AI-scored trade
            if ai_prob_pct != 50.0:
                preds.append(MLPredictionRecord(
                    y_true=y_true,
                    y_prob=ai_prob_pct / 100.0,
                    regime=t.get("regime", "RANGING"),
                ))

        # If an AI walk-forward cache is supplied, also extract fold-level predictions
        if ai_models_cache:
            for k, m in ai_models_cache.items():
                if m.get("is_trained") and "accuracy" in m:
                    # We don't have individual predictions from WF cache, but we can
                    # still surface accuracy/f1 from ai_metrics
                    pass

        return MetricsEngine.compute(
            trades=trades,
            predictions=preds if preds else None,
            initial_balance=initial_balance,
            symbol=symbol,
            timeframe=timeframe,
        )

    # ── Console output ────────────────────────────────────────────────────────

    @staticmethod
    def print_report(report: MetricsReport, width: int = 100) -> None:
        """Pretty-print the full metrics dashboard to stdout."""
        sep  = "=" * width
        hsep = "-" * width
        W    = width

        def row(label: str, value: str, indent: int = 2) -> str:
            pad = " " * indent
            dots = "." * max(1, W - indent - len(label) - len(value) - 2)
            return f"{pad}{label} {dots} {value}"

        def section(title: str) -> str:
            return f"\n{sep}\n  {title}\n{sep}"

        def fmt_pct(v: float, decimals: int = 2) -> str:
            return f"{v:+.{decimals}f}%"

        def fmt_ratio(v: float) -> str:
            if math.isinf(v):
                return "∞"
            return f"{v:.3f}"

        def rating(v: float, thresholds: tuple, labels: tuple) -> str:
            for thr, lbl in zip(thresholds, labels):
                if v >= thr:
                    return lbl
            return labels[-1]

        fm = report.financial
        ml = report.ml
        rg = report.regime

        # ── Header ──────────────────────────────────────────────────────────
        print(section(f"INSTITUTIONAL METRICS REPORT  |  {report.symbol}  |  {report.timeframe}"))
        print(row("Initial Balance",   f"€ {report.initial_balance:,.2f}"))
        print(row("Final Balance",     f"€ {report.final_balance:,.2f}"))
        net_pnl_pct = ((report.final_balance / report.initial_balance) - 1) * 100
        print(row("Net PnL",           f"{fmt_pct(net_pnl_pct)}  (€ {report.final_balance - report.initial_balance:+,.2f})"))

        # ── Trade statistics ─────────────────────────────────────────────────
        print(section("A — TRADE STATISTICS"))
        print(row("Total Trades",      str(fm.total_trades)))
        print(row("  Wins (Full TP)",  str(fm.wins)))
        print(row("  Wins (Partial)",  str(fm.partial_wins)))
        print(row("  Breakevens",      str(fm.breakevens)))
        print(row("  Losses",          str(fm.losses)))
        print(row("Win Rate",          f"{fm.win_rate*100:.2f}%"))
        print(row("Avg Win",           f"€ {fm.avg_win:,.4f}"))
        print(row("Avg Loss",          f"€ {fm.avg_loss:,.4f}  (magnitude)"))
        print(row("Largest Win",       f"€ {fm.largest_win:,.4f}"))
        print(row("Largest Loss",      f"€ {fm.largest_loss:,.4f}  (magnitude)"))

        # ── Financial ratios ─────────────────────────────────────────────────
        print(section("B — FINANCIAL RATIOS  (Institutional KPIs)"))

        exp_rating = rating(fm.expectancy, (50, 20, 5, 0), ("EXCELLENT", "GOOD", "POSITIVE", "MARGINAL"))
        print(row("Expectancy (€/trade)", f"€ {fm.expectancy:+,.4f}   [{exp_rating}]"))

        pf_rating = rating(fm.profit_factor, (3.0, 2.0, 1.5, 1.0), ("EXCEPTIONAL", "STRONG", "GOOD", "WEAK"))
        print(row("Profit Factor", f"{fmt_ratio(fm.profit_factor)}   [{pf_rating}]"))
        print(row("Gain-to-Pain Ratio", fmt_ratio(fm.gain_to_pain)))

        sh_rating = rating(fm.sharpe, (2.0, 1.5, 1.0, 0.5), ("WORLD-CLASS", "EXCELLENT", "GOOD", "ACCEPTABLE"))
        print(row("Sharpe Ratio  (annualised)", f"{fmt_ratio(fm.sharpe)}   [{sh_rating}]"))

        so_rating = rating(fm.sortino, (3.0, 2.0, 1.0, 0.0), ("EXCEPTIONAL", "STRONG", "GOOD", "WEAK"))
        print(row("Sortino Ratio (annualised)", f"{fmt_ratio(fm.sortino)}   [{so_rating}]"))

        ca_rating = rating(fm.calmar, (3.0, 1.5, 0.5, 0.0), ("OUTSTANDING", "STRONG", "ACCEPTABLE", "WEAK"))
        print(row("Calmar Ratio  (CAGR / MaxDD)", f"{fmt_ratio(fm.calmar)}   [{ca_rating}]"))

        print(row("CAGR (proxy)", fmt_pct(fm.cagr_pct)))
        print(row("Annualised Volatility", f"{fm.vol_annualised:.2f}%"))

        # ── Drawdown ─────────────────────────────────────────────────────────
        print(section("C — RISK & DRAWDOWN"))
        print(row("Max Drawdown (€)", f"€ {fm.max_drawdown:,.4f}"))
        print(row("Max Drawdown (%)", f"{fm.max_dd_pct:.2f}%"))
        print(row("Max DD Duration",  f"{fm.max_dd_dur} consecutive losing trades"))

        # ── ML metrics ───────────────────────────────────────────────────────
        if ml.n_samples > 0:
            print(section("D — ML MODEL QUALITY METRICS"))
            print(f"  {'NOTE'}: These metrics evaluate the AI probability engine independently of")
            print(f"  {'      '} trade profitability.  A high AUC model gives better position sizing")
            print(f"  {'      '} via Kelly Criterion and improves entry filtering.\n")
            print(row("Samples Analysed",  str(ml.n_samples)))
            auc_rating = rating(ml.roc_auc, (0.80, 0.70, 0.60, 0.55), ("EXCELLENT", "GOOD", "FAIR", "POOR"))
            print(row("ROC-AUC",           f"{ml.roc_auc:.4f}   [{auc_rating}]"))
            print(row("Precision",         f"{ml.precision:.4f}   (of predicted wins, how many were real wins)"))
            print(row("Recall",            f"{ml.recall:.4f}   (of real wins, how many were caught)"))
            print(row("F1 Score",          f"{ml.f1:.4f}"))

            brier_rating = rating(1 - ml.brier, (0.9, 0.8, 0.7), ("WELL-CALIBRATED", "ACCEPTABLE", "POOR"))
            print(row("Brier Score",       f"{ml.brier:.4f}  (0=perfect, 0.25=random)   [{brier_rating}]"))
            print(row("Calibration Error", f"{ml.ece:.4f}  (Expected Calibration Error — lower is better)"))

            if ml.trending_auc > 0 or ml.ranging_auc > 0:
                print(row("  AUC (TRENDING regime)", f"{ml.trending_auc:.4f}"))
                print(row("  AUC (RANGING regime)",  f"{ml.ranging_auc:.4f}"))

        # ── Regime breakdown ─────────────────────────────────────────────────
        def _fmt_regime(name: str, rfm: FinancialMetrics) -> None:
            print(f"\n  ── {name} ──")
            print(row(f"  Trades",      str(rfm.total_trades),        indent=4))
            print(row(f"  Win Rate",    f"{rfm.win_rate*100:.2f}%",   indent=4))
            print(row(f"  Expectancy",  f"€ {rfm.expectancy:+,.4f}",  indent=4))
            print(row(f"  Sharpe",      fmt_ratio(rfm.sharpe),        indent=4))
            print(row(f"  Max DD %",    f"{rfm.max_dd_pct:.2f}%",     indent=4))

        print(section("E — REGIME-SPECIFIC BREAKDOWN"))
        _fmt_regime("TRENDING MARKET", rg.trending)
        _fmt_regime("RANGING MARKET",  rg.ranging)

        # ── Monthly decomposition ─────────────────────────────────────────────
        if report.monthly:
            print(section("F — MONTHLY PERFORMANCE DECOMPOSITION"))
            hdr = f"  {'Month':<10} {'PnL (€)':>12} {'Trades':>8} {'WinRate':>8} {'Sharpe':>8}"
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for b in report.monthly:
                sign = "+" if b.pnl >= 0 else ""
                print(f"  {b.month:<10} {sign}{b.pnl:>11,.2f} {b.trades:>8} {b.win_rate*100:>7.1f}% {b.sharpe:>8.3f}")

        # ── Rolling windows ───────────────────────────────────────────────────
        if report.rolling:
            print(section("G — ROLLING PERFORMANCE WINDOWS"))
            hdr = f"  {'Window':<20} {'PnL (€)':>12} {'Trades':>8} {'WinRate':>8} {'Sharpe':>8} {'Sortino':>8} {'Vol%':>8}"
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for rw in report.rolling:
                sign = "+" if rw.pnl >= 0 else ""
                print(f"  {rw.window_label:<20} {sign}{rw.pnl:>11,.2f} {rw.n_trades:>8} "
                      f"{rw.win_rate*100:>7.1f}% {rw.sharpe:>8.3f} {rw.sortino:>8.3f} {rw.vol:>7.2f}%")

        # ── Why accuracy fails ───────────────────────────────────────────────
        print(section("H — THEORETICAL NOTE: WHY ACCURACY IS MISLEADING IN TRADING"))
        note = (
            "  Accuracy simply counts correct directional predictions, treating all outcomes equally.\n"
            "  In a system with 3:1 reward-to-risk, a 40% win-rate generates POSITIVE expectancy.\n"
            "  A 70% accurate model with 0.5:1 reward-to-risk has NEGATIVE expectancy and will\n"
            "  eventually ruin the account — regardless of its classification accuracy.\n\n"
            "  The metrics that matter in trading are:\n"
            "    1. Expectancy (E[PnL per trade])  — does the system have a real edge?\n"
            "    2. Sharpe / Sortino               — is the edge realised consistently (risk-adj.)?\n"
            "    3. Calmar ratio                   — how large is the peak loss relative to CAGR?\n"
            "    4. ROC-AUC + Calibration           — is the AI probability meaningful for sizing?\n\n"
            "  Rule: Never optimise accuracy alone. Optimise Expectancy × Trade Frequency.\n"
            "        A well-calibrated model with AUC > 0.65 gives better Kelly sizing,\n"
            "        producing higher Sharpe ratios even at lower raw accuracy."
        )
        print(note)
        print(sep + "\n")

    # ── JSON export ───────────────────────────────────────────────────────────

    @staticmethod
    def export_json(report: MetricsReport, path: str) -> str:
        """Serialise the full MetricsReport to a JSON file. Returns the path."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        def _serialise(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            if math.isinf(obj) if isinstance(obj, float) else False:
                return str(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")

        data = asdict(report)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=_serialise)

        print(f"  [Metrics] JSON report exported → {path}")
        return path

    # ── CSV export ────────────────────────────────────────────────────────────

    @staticmethod
    def export_csv(report: MetricsReport, path: str) -> str:
        """
        Export a flat CSV suitable for Excel / spreadsheet analysis.
        Each metric becomes a row: (category, name, value).
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        rows: List[tuple] = []

        def _add(cat, name, val):
            rows.append((cat, name, val))

        fm = report.financial
        _add("financial", "total_trades",   fm.total_trades)
        _add("financial", "wins",           fm.wins)
        _add("financial", "losses",         fm.losses)
        _add("financial", "win_rate",       round(fm.win_rate, 6))
        _add("financial", "expectancy",     round(fm.expectancy, 4))
        _add("financial", "profit_factor",  round(fm.profit_factor, 4))
        _add("financial", "gain_to_pain",   round(fm.gain_to_pain, 4))
        _add("financial", "sharpe",         round(fm.sharpe, 4))
        _add("financial", "sortino",        round(fm.sortino, 4))
        _add("financial", "calmar",         round(fm.calmar, 4))
        _add("financial", "max_drawdown",   round(fm.max_drawdown, 4))
        _add("financial", "max_dd_pct",     round(fm.max_dd_pct, 4))
        _add("financial", "cagr_pct",       round(fm.cagr_pct, 4))
        _add("financial", "vol_annualised", round(fm.vol_annualised, 4))

        ml = report.ml
        _add("ml", "n_samples",  ml.n_samples)
        _add("ml", "roc_auc",    round(ml.roc_auc, 6))
        _add("ml", "precision",  round(ml.precision, 6))
        _add("ml", "recall",     round(ml.recall, 6))
        _add("ml", "f1",         round(ml.f1, 6))
        _add("ml", "brier",      round(ml.brier, 6))
        _add("ml", "ece",        round(ml.ece, 6))

        df = pd.DataFrame(rows, columns=["category", "metric", "value"])
        df.to_csv(path, index=False)
        print(f"  [Metrics] CSV report exported → {path}")
        return path

    # ── Chart generation ──────────────────────────────────────────────────────

    @staticmethod
    def export_charts(
        report: MetricsReport,
        trades: List[TradeRecord],
        output_dir: str = "data/metrics_charts",
    ) -> List[str]:
        """
        Generate and save a suite of diagnostic charts.
        Returns a list of saved file paths.

        Charts produced
        ---------------
        1. equity_curve.png         — Equity curve + drawdown band
        2. drawdown.png             — Drawdown time-series
        3. monthly_pnl.png          — Monthly P&L bar chart
        4. rolling_sharpe.png       — 30-trade rolling Sharpe
        5. pnl_distribution.png     — Histogram of trade PnL
        6. calibration.png          — Reliability diagram (requires ML preds)
        """
        if not MATPLOTLIB_AVAILABLE:
            print("  [Metrics] matplotlib not available — skipping chart generation.")
            return []

        os.makedirs(output_dir, exist_ok=True)
        paths: List[str] = []

        # Palette
        C_EQUITY  = "#4FC3F7"
        C_DD      = "#EF5350"
        C_WIN     = "#66BB6A"
        C_LOSS    = "#EF5350"
        C_NEUTRAL = "#90A4AE"
        BG        = "#0D1117"
        FG        = "#E6EDF3"
        GRID      = "#21262D"

        style = {
            "figure.facecolor":  BG,
            "axes.facecolor":    BG,
            "axes.edgecolor":    GRID,
            "axes.labelcolor":   FG,
            "text.color":        FG,
            "xtick.color":       FG,
            "ytick.color":       FG,
            "grid.color":        GRID,
            "grid.linestyle":    "--",
            "grid.linewidth":    0.5,
        }

        pnl_arr    = np.array([t.pnl for t in trades], dtype=float)
        equity_arr = report.initial_balance + np.cumsum(pnl_arr)
        dd_arr, _, _, _ = _drawdown_series(equity_arr)
        x_idx      = np.arange(len(equity_arr))

        # ── 1. Equity Curve ──────────────────────────────────────────────────
        with plt.rc_context(style):
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                           gridspec_kw={"height_ratios": [3, 1]})
            fig.suptitle(f"Equity Curve & Drawdown  |  {report.symbol} {report.timeframe}",
                         fontsize=14, fontweight="bold", color=FG)

            ax1.plot(x_idx, equity_arr, color=C_EQUITY, linewidth=1.5, label="Equity")
            ax1.fill_between(x_idx, equity_arr, report.initial_balance,
                             where=(equity_arr >= report.initial_balance),
                             alpha=0.15, color=C_WIN)
            ax1.fill_between(x_idx, equity_arr, report.initial_balance,
                             where=(equity_arr < report.initial_balance),
                             alpha=0.15, color=C_LOSS)
            ax1.axhline(report.initial_balance, color=C_NEUTRAL, linestyle="--",
                        linewidth=0.8, label=f"Start € {report.initial_balance:,.0f}")
            ax1.set_ylabel("Portfolio Value (€)")
            ax1.legend(loc="upper left", framealpha=0.0)
            ax1.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda v, _: f"€{v:,.0f}"))
            ax1.grid(True)

            ax2.fill_between(x_idx, dd_arr, 0, color=C_DD, alpha=0.6)
            ax2.plot(x_idx, dd_arr, color=C_DD, linewidth=0.8)
            ax2.set_ylabel("Drawdown (€)")
            ax2.set_xlabel("Trade Number")
            ax2.grid(True)

            plt.tight_layout()
            p = os.path.join(output_dir, "equity_curve.png")
            plt.savefig(p, dpi=150, bbox_inches="tight")
            plt.close()
            paths.append(p)

        # ── 2. Monthly P&L bars ──────────────────────────────────────────────
        if report.monthly:
            with plt.rc_context(style):
                fig, ax = plt.subplots(figsize=(max(8, len(report.monthly) * 0.7 + 2), 5))
                months  = [b.month for b in report.monthly]
                pnls    = [b.pnl   for b in report.monthly]
                colors  = [C_WIN if p >= 0 else C_LOSS for p in pnls]

                bars = ax.bar(months, pnls, color=colors, edgecolor="#00000033", linewidth=0.5)
                ax.axhline(0, color=C_NEUTRAL, linewidth=0.8)
                ax.set_title("Monthly P&L Decomposition", fontsize=13, fontweight="bold")
                ax.set_ylabel("PnL (€)")
                ax.set_xlabel("Month")
                ax.tick_params(axis="x", rotation=45)

                for bar, val in zip(bars, pnls):
                    label = f"€{val:+,.1f}"
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + (max(pnls) * 0.02 if val >= 0 else min(pnls) * 0.02),
                            label, ha="center", va="bottom" if val >= 0 else "top",
                            fontsize=7, color=FG)

                ax.grid(axis="y")
                plt.tight_layout()
                p = os.path.join(output_dir, "monthly_pnl.png")
                plt.savefig(p, dpi=150, bbox_inches="tight")
                plt.close()
                paths.append(p)

        # ── 3. PnL distribution ──────────────────────────────────────────────
        if len(pnl_arr) >= 3:
            with plt.rc_context(style):
                fig, ax = plt.subplots(figsize=(10, 5))
                bins = min(50, max(10, len(pnl_arr) // 3))
                win_pnl  = pnl_arr[pnl_arr > 0]
                loss_pnl = pnl_arr[pnl_arr < 0]

                if len(win_pnl):
                    ax.hist(win_pnl, bins=bins, color=C_WIN, alpha=0.7, label="Wins")
                if len(loss_pnl):
                    ax.hist(loss_pnl, bins=bins, color=C_LOSS, alpha=0.7, label="Losses")

                ax.axvline(float(np.mean(pnl_arr)), color="gold", linewidth=1.5,
                           linestyle="--", label=f"Avg PnL €{float(np.mean(pnl_arr)):+.2f}")
                ax.axvline(report.financial.expectancy, color="cyan", linewidth=1.5,
                           linestyle=":", label=f"Expectancy €{report.financial.expectancy:+.2f}")
                ax.set_title("Trade PnL Distribution", fontsize=13, fontweight="bold")
                ax.set_xlabel("PnL per Trade (€)")
                ax.set_ylabel("Frequency")
                ax.legend(framealpha=0.0)
                ax.grid(True)
                plt.tight_layout()
                p = os.path.join(output_dir, "pnl_distribution.png")
                plt.savefig(p, dpi=150, bbox_inches="tight")
                plt.close()
                paths.append(p)

        # ── 4. Rolling 30-trade Sharpe ───────────────────────────────────────
        if len(pnl_arr) >= 35:
            with plt.rc_context(style):
                WIN_SIZE = 30
                ret_arr  = pnl_arr / report.initial_balance
                roll_sharpe = []
                for i in range(WIN_SIZE, len(ret_arr)):
                    roll_sharpe.append(_sharpe(ret_arr[i - WIN_SIZE:i]))

                xs = np.arange(WIN_SIZE, len(ret_arr))
                fig, ax = plt.subplots(figsize=(14, 4))
                ax.plot(xs, roll_sharpe, color=C_EQUITY, linewidth=1.2)
                ax.fill_between(xs, roll_sharpe, 0,
                                where=np.array(roll_sharpe) >= 0, alpha=0.2, color=C_WIN)
                ax.fill_between(xs, roll_sharpe, 0,
                                where=np.array(roll_sharpe) < 0, alpha=0.2, color=C_LOSS)
                ax.axhline(0,   color=C_NEUTRAL, linestyle="--", linewidth=0.8)
                ax.axhline(1.0, color=C_WIN,     linestyle=":",  linewidth=0.8, label="Sharpe = 1.0 (good)")
                ax.axhline(2.0, color="gold",    linestyle=":",  linewidth=0.8, label="Sharpe = 2.0 (excellent)")
                ax.set_title(f"Rolling {WIN_SIZE}-Trade Sharpe Ratio", fontsize=13, fontweight="bold")
                ax.set_xlabel("Trade Number")
                ax.set_ylabel("Sharpe Ratio")
                ax.legend(framealpha=0.0)
                ax.grid(True)
                plt.tight_layout()
                p = os.path.join(output_dir, "rolling_sharpe.png")
                plt.savefig(p, dpi=150, bbox_inches="tight")
                plt.close()
                paths.append(p)

        # ── 5. Calibration diagram ───────────────────────────────────────────
        if SKLEARN_AVAILABLE and report.ml.n_samples >= 20:
            # We need raw predictions — fetch them from report metadata via
            # a reconstructed set if available.  We'll do a best-effort attempt
            # using win-rate vs avg ai_prob in trades that have ai_prob != 50.
            ai_prob_arr = np.array([t.ai_prob / 100.0 for t in trades
                                    if t.ai_prob not in (50.0, 50)], dtype=float)
            y_true_arr  = np.array([1 if t.result in ("WIN", "WIN_PARTIAL") else 0
                                    for t in trades if t.ai_prob not in (50.0, 50)], dtype=int)

            if len(ai_prob_arr) >= 20 and len(np.unique(y_true_arr)) > 1:
                try:
                    frac_pos, mean_pred = calibration_curve(
                        y_true_arr, ai_prob_arr, n_bins=min(10, len(ai_prob_arr) // 3),
                        strategy="quantile"
                    )
                    with plt.rc_context(style):
                        fig, ax = plt.subplots(figsize=(7, 7))
                        ax.plot([0, 1], [0, 1], linestyle="--", color=C_NEUTRAL,
                                linewidth=1.2, label="Perfect Calibration")
                        ax.plot(mean_pred, frac_pos, marker="o", color=C_EQUITY,
                                linewidth=1.5, markersize=6, label="Model Calibration")
                        ax.fill_between(mean_pred, mean_pred, frac_pos,
                                        alpha=0.15, color=C_EQUITY)
                        ax.set_title("Reliability Diagram (Probability Calibration)",
                                     fontsize=13, fontweight="bold")
                        ax.set_xlabel("Mean Predicted Probability")
                        ax.set_ylabel("Fraction of Positives (Actual Win Rate)")
                        ax.legend(framealpha=0.0)
                        ax.grid(True)
                        ax.set_xlim(0, 1)
                        ax.set_ylim(0, 1)
                        plt.tight_layout()
                        p = os.path.join(output_dir, "calibration.png")
                        plt.savefig(p, dpi=150, bbox_inches="tight")
                        plt.close()
                        paths.append(p)
                except Exception as exc:
                    print(f"  [Metrics] Calibration chart skipped: {exc}")

        print(f"  [Metrics] {len(paths)} charts saved to '{output_dir}':")
        for p in paths:
            print(f"    → {p}")

        return paths


# ════════════════════════════════════════════════════════════════════════════
# §4 — CONVENIENCE ADAPTER  (plug directly into backtest_lab)
# ════════════════════════════════════════════════════════════════════════════

def evaluate_backtest_profile(
    backtest_result:  dict,
    initial_balance:  float  = 1000.0,
    profile_name:     str    = "Unknown",
    output_dir:       str    = "data/metrics",
    generate_charts:  bool   = True,
    export_json:      bool   = True,
    export_csv_file:  bool   = True,
    print_table:      bool   = True,
) -> MetricsReport:
    """
    High-level one-shot function for integration with backtest_lab.run_backtest().

    Parameters
    ----------
    backtest_result : dict output of simulate_backtest() for a single risk profile
    initial_balance : starting equity
    profile_name    : risk profile label for file naming
    output_dir      : root directory for all output artefacts
    generate_charts : whether to render and save charts
    export_json     : whether to save a JSON metrics report
    export_csv_file : whether to save a flat CSV metrics report
    print_table     : whether to print the full dashboard to stdout

    Returns
    -------
    MetricsReport with all computed metrics
    """
    safe_name = profile_name.replace(" ", "_").replace("(", "").replace(")", "").lower()
    os.makedirs(output_dir, exist_ok=True)

    report = MetricsEngine.from_backtest_output(
        backtest_result=backtest_result,
        initial_balance=initial_balance,
    )

    if print_table:
        MetricsEngine.print_report(report)

    if export_json:
        MetricsEngine.export_json(report, os.path.join(output_dir, f"{safe_name}_metrics.json"))

    if export_csv_file:
        MetricsEngine.export_csv(report, os.path.join(output_dir, f"{safe_name}_metrics.csv"))

    if generate_charts and MATPLOTLIB_AVAILABLE:
        trades = [
            TradeRecord(
                pnl=float(t.get("pnl", 0.0)),
                result=t.get("result", "LOSS"),
                side=t.get("side", "BUY"),
                regime=t.get("regime", "RANGING"),
                ai_prob=float(t.get("ai_prob", 50.0)),
            )
            for t in backtest_result.get("trades", [])
        ]
        MetricsEngine.export_charts(
            report=report,
            trades=trades,
            output_dir=os.path.join(output_dir, f"{safe_name}_charts"),
        )

    return report


# ════════════════════════════════════════════════════════════════════════════
# §5 — STANDALONE DEMO
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Standalone self-test: generate synthetic trade + prediction data,
    compute all metrics, print the report, export artefacts.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    rng = np.random.default_rng(42)
    N_TRADES = 120

    # Simulate a system with ~55% win rate, avg win = €80, avg loss = €40  (2:1 RR)
    results_pool = ["WIN"] * 33 + ["LOSS"] * 27 + ["BREAKEVEN"] * 5 + ["WIN_PARTIAL"] * 5
    regimes      = rng.choice(["TRENDING", "RANGING"], size=N_TRADES, p=[0.4, 0.6])

    trades: List[TradeRecord] = []
    preds:  List[MLPredictionRecord] = []
    balance = 1000.0

    for i in range(N_TRADES):
        r = results_pool[i % len(results_pool)]
        if r in ("WIN", "WIN_PARTIAL"):
            pnl     = float(rng.normal(80, 20))
            ai_prob = float(min(99, rng.normal(78, 12)))
        elif r == "LOSS":
            pnl     = float(rng.normal(-40, 12))
            ai_prob = float(max(1, rng.normal(42, 15)))
        else:
            pnl     = float(rng.normal(-2, 1))
            ai_prob = 50.0

        balance += pnl
        trades.append(TradeRecord(
            pnl=pnl,
            result=r,
            regime=str(regimes[i]),
            ai_prob=ai_prob,
            balance_after=balance,
            entry_time=pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
        ))
        if ai_prob != 50.0:
            preds.append(MLPredictionRecord(
                y_true=1 if r in ("WIN", "WIN_PARTIAL") else 0,
                y_prob=ai_prob / 100.0,
                regime=str(regimes[i]),
            ))

    report = MetricsEngine.compute(
        trades=trades,
        predictions=preds,
        initial_balance=1000.0,
        symbol="BTC/USDT",
        timeframe="15m",
    )
    MetricsEngine.print_report(report)
    MetricsEngine.export_json(report, "data/metrics_demo.json")
    MetricsEngine.export_csv(report,  "data/metrics_demo.csv")
    MetricsEngine.export_charts(report, trades, "data/metrics_demo_charts")
    print("\n[Demo] All artefacts written to ./data/")
