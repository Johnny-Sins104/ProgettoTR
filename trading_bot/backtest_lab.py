"""
backtest_lab.py — Simulazione isolata con Regime Switching, Ordini Pendenti e Profili di Rischio Multipli (Compounding).
"""
import asyncio
import os
import time
import sys
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


from config import Config
from core.client import ExchangeClient
from core.analyzer import TechnicalAnalyzer
from core.engine import DecisionEngine
from core.risk import DynamicRiskEngine, RiskManager
from core.visualizer import save_trade_chart
from core.ai_engine import TradingAI
from core.signal_density import SignalDensityMonitor
from core.cost_aware_meta import CostAwareMetaLabeler
from core.runtime_profiler import get_runtime_profiler
from core.execution_cost_model import ExecutionCostModel
from core.asset_archetype_gating import evaluate_asset_archetype_gate

CHARTS_DIR = "data/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

# ------------------------------------------------------------------ #
#  PARAMETRI SIMULAZIONE                                               #
# ------------------------------------------------------------------ #
INITIAL_BALANCE  = 1000.0   # €
COMMISSION_RATE  = Config.COMMISSION_RATE  # Centralizzato in Config (Futures: 0.02% per side)


def _execution_cost_for_trade(
    *,
    size: float,
    entry_price: float,
    exit_price: float,
    side: str,
    atr_val: float = 0.0,
    atr_pct: float = 0.0,
    atr_ratio: float = 1.0,
    vol_regime: str = "NORMAL",
    order_type: str = "LIMIT",
    entry_type: str = "BREAKOUT",
) -> tuple[float, dict]:
    """Return deterministic round-trip execution friction for a closed trade leg.

    NOTE: Metodologicamente, il backtest applica la friction (slippage e fee)
    detraendola dal PnL complessivo al termine del trade, a differenza dell'engine
    live/paper che calcola lo slippage in tempo reale all'ingresso/uscita
    spostando fisicamente i livelli SL/TP. Questo modello offline stima con
    accuratezza l'impatto economico complessivo pur mantenendo la stabilità dei
    trigger storici.
    """
    notional = abs(float(size or 0.0)) * max(0.0, float(entry_price or exit_price or 0.0))
    try:
        est = ExecutionCostModel.estimate_round_trip_bps(
            price=float(entry_price or exit_price or 0.0),
            atr_val=float(atr_val or 0.0),
            atr_pct=float(atr_pct or 0.0),
            atr_ratio=float(atr_ratio or 1.0),
            vol_regime=str(vol_regime or "NORMAL"),
            order_type=str(order_type or "LIMIT"),
            entry_type=str(entry_type or "BREAKOUT"),
            symbol=getattr(Config, "SYMBOL", "BTC/USDT"),
            timeframe=getattr(Config, "TIMEFRAME", "15m"),
            cost_model=getattr(Config, "EXECUTION_COST_MODEL", "base"),
        )
        return ExecutionCostModel.cost_amount(notional, est), est.to_dict()
    except Exception:
        fallback = notional * COMMISSION_RATE * 2.0
        return fallback, {
            "cost_model": "legacy_commission_fallback",
            "total_round_trip_cost_bps": float(COMMISSION_RATE * 2.0 * 10000.0),
            "fee_bps_round_trip": float(COMMISSION_RATE * 2.0 * 10000.0),
        }



# ------------------------------------------------------------------ #
#  BACKTEST LIFECYCLE HELPERS                                         #
# ------------------------------------------------------------------ #
def _row_time(row) -> str:
    return str(row["datetime"]) if "datetime" in row else str(row.name)


def _canonical_trade_pnl(trade: dict) -> float:
    from core.backtest_lifecycle import canonical_trade_pnl
    return canonical_trade_pnl(trade)


def _apply_trade_close(
    *,
    trades: list,
    risk_mgr: DynamicRiskEngine,
    df: pd.DataFrame,
    row,
    open_trade: dict,
    result: str,
    realized_pnl: float,
    balance_before: float,
    balance_after: float,
    peak_balance: float,
    max_drawdown: float,
    save_charts: bool,
    sl_for_report: float,
    tp_for_report: float,
) -> tuple[float, float, dict]:
    """Close a trade through one canonical lifecycle path.

    This function is the single source of truth for closed-trade accounting:
    it updates equity state, appends the closed trade, emits the risk event and
    optionally creates the visualizer artifact.  Keeping this centralized avoids
    the historical failure mode where balance changed but risk analytics still
    reported zero analysed trades.
    """
    risk_mgr.update_equity(balance_after)

    if balance_after > peak_balance:
        peak_balance = balance_after
    dd = (peak_balance - balance_after) / peak_balance * 100 if peak_balance > 0 else 0.0
    if dd > max_drawdown:
        max_drawdown = dd

    trade_num = len(trades) + 1
    side = open_trade["side"]
    entry = float(open_trade["entry"])

    trade = {
        "side": side,
        "result": result,
        "pnl": float(realized_pnl),
        "realized_pnl": float(realized_pnl),
        "balance_before": float(balance_before),
        "balance_after": float(balance_after),
        "balance": float(balance_after),
        "entry": entry,
        "sl": float(sl_for_report),
        "tp": float(tp_for_report),
        "position_size": float(open_trade.get("size", 0.0) or 0.0),
        "effective_leverage": float(open_trade.get("effective_leverage", 0.0) or 0.0),
        "risk_snapshot_trade_num": open_trade.get("risk_snapshot_trade_num"),
        "risk_snapshot_pct": float(open_trade.get("risk_snapshot_pct", 0.0) or 0.0),
        "confluence_comb": open_trade.get("confluence_comb", "None"),
        "ai_prob": open_trade.get("ai_prob", 50.0),
        "entry_time": open_trade["entry_time"],
        "exit_time": _row_time(row),
        "regime": open_trade["regime"],
        "adx": open_trade["adx"],
        "atr_pct": open_trade["atr_pct"],
        "volume": open_trade["volume"],
        "volume_ratio": open_trade["volume_ratio"],
        "close_vs_ema": open_trade["close_vs_ema"],
        "setup_quality": open_trade.get("setup_quality", 0.0),
        "setup_archetype": open_trade.get("setup_archetype", "UNKNOWN"),
        "structure_score": float(open_trade.get("structure_score", 0.0) or 0.0),
        "edge_adjustment_r": float(open_trade.get("edge_adjustment_r", 0.0) or 0.0),
        "execution_cost_model": str(getattr(Config, "EXECUTION_COST_MODEL", "base")),
        "execution_cost_total": float(open_trade.get("execution_cost_total", 0.0) or 0.0),
        "execution_cost_bps": float(open_trade.get("execution_cost_bps", 0.0) or 0.0),
        "execution_cost_details": open_trade.get("execution_cost_details", []),
    }

    trades.append(trade)
    risk_mgr.record_trade_event(trade, balance_before, balance_after)

    if save_charts:
        chart_path = f"{CHARTS_DIR}/trade_{trade_num:03d}_{result}.html"
        save_trade_chart(
            df=open_trade["window_df"],
            trade_data={"side": side, "entry": entry, "sl": sl_for_report, "tp": tp_for_report},
            filename=chart_path,
        )

    return peak_balance, max_drawdown, trade


def _write_lifecycle_report(
    result: dict,
    output_path: str = "data/lifecycle_consistency_report.json",
    *,
    charting_enabled: bool | None = None,
) -> dict:
    from core.backtest_lifecycle import write_lifecycle_report

    if charting_enabled is None:
        charting_enabled = bool(getattr(Config, "BACKTEST_SAVE_CHARTS", True))
    return write_lifecycle_report(
        result,
        CHARTS_DIR,
        output_path,
        charting_enabled=bool(charting_enabled),
    )


# ------------------------------------------------------------------ #
#  PROMPT 28.4: ARCHETYPE-CONDITIONED META GATING                    #
# ------------------------------------------------------------------ #
def _archetype_gate_config(archetype: str) -> dict:
    """Return conservative decision gates for a setup archetype.

    The global meta threshold is not enough once market-structure features are
    propagated: the last diagnostic run accepted 100% of technical candidates
    while realized PnL stayed negative.  These gates keep each archetype from
    passing unless its own structural evidence, quality and net edge are above
    a minimally credible floor.
    """
    arch = str(archetype or "UNKNOWN").upper()
    table = {
        "HTF_ALIGNED_PULLBACK": {
            "min_prob": getattr(Config, "SETUP_HTF_MIN_PROB", 50.0),
            "min_quality": getattr(Config, "SETUP_HTF_MIN_QUALITY", 58.0),
            "min_structure": getattr(Config, "SETUP_HTF_MIN_STRUCTURE", 62.0),
            "min_net_edge": getattr(Config, "SETUP_HTF_MIN_NET_EDGE_R", 0.10),
        },
        "VOL_COMPRESSION_BREAKOUT": {
            "min_prob": getattr(Config, "SETUP_VOL_BREAKOUT_MIN_PROB", 52.0),
            "min_quality": getattr(Config, "SETUP_VOL_BREAKOUT_MIN_QUALITY", 62.0),
            "min_structure": getattr(Config, "SETUP_VOL_BREAKOUT_MIN_STRUCTURE", 65.0),
            "min_net_edge": getattr(Config, "SETUP_VOL_BREAKOUT_MIN_NET_EDGE_R", 0.15),
        },
        "LIQUIDITY_SWEEP_REVERSAL": {
            "min_prob": getattr(Config, "SETUP_SWEEP_MIN_PROB", 52.0),
            "min_quality": getattr(Config, "SETUP_SWEEP_MIN_QUALITY", 60.0),
            "min_structure": getattr(Config, "SETUP_SWEEP_MIN_STRUCTURE", 62.0),
            "min_net_edge": getattr(Config, "SETUP_SWEEP_MIN_NET_EDGE_R", 0.12),
        },
        "SESSION_MOMENTUM": {
            "min_prob": getattr(Config, "SETUP_SESSION_MIN_PROB", 54.0),
            "min_quality": getattr(Config, "SETUP_SESSION_MIN_QUALITY", 62.0),
            "min_structure": getattr(Config, "SETUP_SESSION_MIN_STRUCTURE", 65.0),
            "min_net_edge": getattr(Config, "SETUP_SESSION_MIN_NET_EDGE_R", 0.15),
        },
        "RANGING_MEAN_REVERSION": {
            "min_prob": getattr(Config, "SETUP_MR_MIN_PROB", 55.0),
            "min_quality": getattr(Config, "SETUP_MR_MIN_QUALITY", 60.0),
            "min_structure": getattr(Config, "SETUP_MR_MIN_STRUCTURE_SCORE", 52.0),
            "min_net_edge": getattr(Config, "SETUP_MR_MIN_NET_EDGE_R", 0.18),
        },
    }
    return table.get(arch, {
        "min_prob": getattr(Config, "META_PROB_THRESHOLD", 55.0),
        "min_quality": getattr(Config, "META_QUALITY_THRESHOLD", 50.0),
        "min_structure": getattr(Config, "SETUP_STRUCTURE_MIN_SCORE", 20.0),
        "min_net_edge": getattr(Config, "META_MIN_NET_EDGE_R", 0.0),
    })


def _passes_archetype_gate(*, archetype: str, p_cal: float, setup_quality: float, structure_score: float, expected_net_edge_r: float) -> tuple[bool, str, dict]:
    if not getattr(Config, "SETUP_ARCHETYPE_GATING_ENABLED", True):
        return True, "", {}
    gates = {k: float(v) for k, v in _archetype_gate_config(archetype).items()}
    checks = {
        "probability": float(p_cal) >= gates["min_prob"],
        "quality": float(setup_quality) >= gates["min_quality"],
        "structure": float(structure_score) >= gates["min_structure"],
        "net_edge": float(expected_net_edge_r) >= gates["min_net_edge"],
    }
    if all(checks.values()):
        return True, "", {"gates": gates, "checks": checks}
    failed = [name for name, ok in checks.items() if not ok]
    reason = "archetype_gate_" + str(archetype or "UNKNOWN").lower() + "_" + "_".join(failed)
    return False, reason, {"gates": gates, "checks": checks}


def _disabled_archetypes_from_config() -> set[str]:
    raw_values = [str(getattr(Config, "SETUP_DISABLED_ARCHETYPES", "") or "")]
    timeframe = str(getattr(Config, "TIMEFRAME", "15m") or "15m").lower()
    if timeframe == "5m":
        raw_values.append(str(getattr(Config, "SETUP_DISABLED_ARCHETYPES_5M", "") or ""))
    elif timeframe == "3m":
        raw_values.append(str(getattr(Config, "SETUP_DISABLED_ARCHETYPES_3M", "") or ""))
    out: set[str] = set()
    for raw in raw_values:
        out.update({x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()})
    return out


def _negative_realized_archetypes_from_report() -> set[str]:
    if not bool(getattr(Config, "SETUP_AUTO_DISABLE_NEGATIVE_ARCHETYPES", True)):
        return set()
    path = str(getattr(Config, "SETUP_NEGATIVE_ARCHETYPE_REPORT_PATH", "data/archetype_performance_report.json"))
    if not os.path.exists(path):
        return set()
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        min_trades = int(getattr(Config, "SETUP_NEGATIVE_ARCHETYPE_MIN_TRADES", 5))
        max_avg_r = float(getattr(Config, "SETUP_NEGATIVE_ARCHETYPE_AVG_R_MAX", -0.05))
        rows = report.get("archetypes", report)
        disabled = set()
        if isinstance(rows, dict):
            for name, row in rows.items():
                if not isinstance(row, dict):
                    continue
                trades = int(row.get("trades", 0) or 0)
                avg_r = float(row.get("avg_r", row.get("avgR", 0.0)) or 0.0)
                if trades >= min_trades and avg_r <= max_avg_r:
                    disabled.add(str(name).upper())
        return disabled
    except Exception:
        return set()


def _archetype_block_reason(archetype: str) -> str:
    arch = str(archetype or "UNKNOWN").upper()
    asset_gate = evaluate_asset_archetype_gate(
        Config,
        symbol=getattr(Config, "SYMBOL", "BTC/USDT"),
        archetype=arch,
        cost_model=getattr(Config, "EXECUTION_COST_MODEL", "base"),
    )
    if not asset_gate.allowed:
        return str(asset_gate.reason or "asset_archetype_gate_block").lower()
    if arch in _disabled_archetypes_from_config():
        return "archetype_disabled_static_" + arch.lower()
    if arch in _negative_realized_archetypes_from_report():
        return "archetype_disabled_negative_realized_" + arch.lower()
    return ""


def _ai_prediction_diagnostics(ai, features: dict, *, active_fold, p_cal: float, prediction_source: str) -> dict:
    if not bool(getattr(Config, "AI_PREDICTION_AUDIT", True)):
        return {}
    try:
        from core.meta_labeling import FEATURE_NAMES
    except Exception:
        FEATURE_NAMES = []
    missing = [name for name in FEATURE_NAMES if name not in features]
    manager = getattr(ai, "manager", None)
    models = getattr(manager, "models", {}) if manager is not None else {}
    model_ready = bool(ai.is_ready()) if hasattr(ai, "is_ready") else False
    return {
        "model_ready": model_ready,
        "manager_trained": bool(getattr(manager, "is_trained", False)) if manager is not None else False,
        "active_fold_start": getattr(active_fold, "test_start", None) if active_fold is not None else None,
        "active_model_key": getattr(ai, "_active_model_key", None),
        "active_model_source": getattr(ai, "_active_model_source", "GLOBAL"),
        "prediction_source": prediction_source,
        "p_cal": float(p_cal),
        "neutral_probability": abs(float(p_cal) - 50.0) < 1e-9,
        "feature_count": len(features),
        "expected_feature_count": len(FEATURE_NAMES),
        "missing_feature_count": len(missing),
        "missing_features": missing[:20],
        "models_available": sorted([str(k) for k, v in models.items() if v is not None]),
    }


def _safe_parse_ts(value):
    try:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def _trade_r_value(trade: dict) -> float:
    pnl = float(trade.get("realized_pnl", trade.get("pnl", 0.0)) or 0.0)
    balance_before = float(trade.get("balance_before", 0.0) or 0.0)
    risk_pct = float(trade.get("risk_snapshot_pct", 0.0) or 0.0)
    risk_capital = abs(balance_before * risk_pct)
    return pnl / risk_capital if risk_capital > 0 else 0.0


def _aggregate_trade_bucket(items: list[dict]) -> dict:
    pnls = [float(t.get("realized_pnl", t.get("pnl", 0.0)) or 0.0) for t in items]
    r_values = [_trade_r_value(t) for t in items]
    wins = sum(1 for t in items if str(t.get("result")) == "WIN")
    partials = sum(1 for t in items if str(t.get("result")) == "WIN_PARTIAL")
    losses = sum(1 for t in items if str(t.get("result")) == "LOSS")
    breakevens = sum(1 for t in items if str(t.get("result")) == "BREAKEVEN")
    resolved = wins + partials + losses
    return {
        "trades": len(items),
        "wins": wins,
        "partial_wins": partials,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate_pct": round(((wins + partials) / resolved * 100.0) if resolved else 0.0, 4),
        "total_pnl": round(sum(pnls), 6),
        "avg_pnl": round((sum(pnls) / len(pnls)) if pnls else 0.0, 6),
        "avg_r": round((sum(r_values) / len(r_values)) if r_values else 0.0, 6),
        "median_r": round(float(pd.Series(r_values).median()) if r_values else 0.0, 6),
        "min_r": round(min(r_values) if r_values else 0.0, 6),
        "max_r": round(max(r_values) if r_values else 0.0, 6),
    }


def _volatility_bucket(trade: dict) -> str:
    atr_pct = float(trade.get("atr_pct", 0.0) or 0.0)
    if atr_pct <= 0:
        return "UNKNOWN"
    if atr_pct >= float(getattr(Config, "EDGE_STABILITY_HIGH_ATR_PCT", 0.75)):
        return "HIGH_VOL"
    if atr_pct <= float(getattr(Config, "EDGE_STABILITY_LOW_ATR_PCT", 0.30)):
        return "LOW_VOL"
    return "NORMAL_VOL"


def _build_archetype_performance_report(trades: list, output_path: str = "data/archetype_performance_report.json") -> dict:
    """Aggregate realized closed-trade performance by setup archetype and stability slices."""
    import json
    from collections import defaultdict

    by_arch = defaultdict(list)
    by_arch_month = defaultdict(list)
    by_arch_side = defaultdict(list)
    by_arch_regime = defaultdict(list)
    by_arch_vol = defaultdict(list)

    for trade in trades or []:
        arch = str(trade.get("setup_archetype", "UNKNOWN") or "UNKNOWN")
        by_arch[arch].append(trade)

        entry_ts = _safe_parse_ts(trade.get("entry_time"))
        month = entry_ts.strftime("%Y-%m") if entry_ts is not None else "UNKNOWN"
        side = str(trade.get("side", "UNKNOWN") or "UNKNOWN")
        regime = str(trade.get("regime", "UNKNOWN") or "UNKNOWN")
        vol_bucket = _volatility_bucket(trade)

        by_arch_month[f"{arch}|{month}"].append(trade)
        by_arch_side[f"{arch}|{side}"].append(trade)
        by_arch_regime[f"{arch}|{regime}"].append(trade)
        by_arch_vol[f"{arch}|{vol_bucket}"].append(trade)

    rows = {k: _aggregate_trade_bucket(v) for k, v in sorted(by_arch.items())}

    def split_rows(bucket: dict, key_names: tuple[str, str]) -> dict:
        out = {}
        for compound, items in sorted(bucket.items()):
            left, right = compound.split("|", 1)
            out.setdefault(left, {})[right] = _aggregate_trade_bucket(items)
        return out

    min_trades = int(getattr(Config, "EDGE_STABILITY_MIN_TRADES_PER_ARCHETYPE", 20))
    positive_avg_r_floor = float(getattr(Config, "EDGE_STABILITY_MIN_AVG_R", 0.05))
    warnings = []
    for arch, row in rows.items():
        if int(row.get("trades", 0)) < min_trades:
            warnings.append(
                f"{arch}: LOW_SAMPLE trades={row.get('trades', 0)} < {min_trades}; treat expectancy as provisional."
            )
        if int(row.get("trades", 0)) >= min_trades and float(row.get("avg_r", 0.0)) < positive_avg_r_floor:
            warnings.append(
                f"{arch}: WEAK_OR_NEGATIVE_EDGE avgR={row.get('avg_r', 0.0):+.3f} below {positive_avg_r_floor:+.3f}."
            )

    report = {
        "by_archetype": rows,
        "by_archetype_month": split_rows(by_arch_month, ("archetype", "month")),
        "by_archetype_side": split_rows(by_arch_side, ("archetype", "side")),
        "by_archetype_regime": split_rows(by_arch_regime, ("archetype", "regime")),
        "by_archetype_volatility_bucket": split_rows(by_arch_vol, ("archetype", "vol_bucket")),
        "stability_warnings": warnings,
        "guardrails": {
            "min_trades_per_archetype": min_trades,
            "min_avg_r": positive_avg_r_floor,
        },
        "total_trades": len(trades or []),
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def _export_equity_curve_and_monthly_report(
    trades: list,
    initial_balance: float = INITIAL_BALANCE,
    equity_path: str = "data/equity_curve.csv",
    monthly_path: str = "data/monthly_performance_report.json",
) -> dict:
    """Export closed-trade equity curve plus monthly realized performance diagnostics."""
    import json
    from collections import defaultdict

    os.makedirs(os.path.dirname(equity_path), exist_ok=True)
    rows = []
    equity = float(initial_balance)
    peak = equity
    rows.append({
        "trade_num": 0,
        "entry_time": "",
        "exit_time": "",
        "setup_archetype": "START",
        "side": "",
        "result": "START",
        "realized_pnl": 0.0,
        "r_value": 0.0,
        "balance": equity,
        "drawdown_pct": 0.0,
    })
    for idx, trade in enumerate(trades or [], start=1):
        equity = float(trade.get("balance_after", trade.get("balance", equity)) or equity)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
        rows.append({
            "trade_num": idx,
            "entry_time": trade.get("entry_time", ""),
            "exit_time": trade.get("exit_time", ""),
            "setup_archetype": trade.get("setup_archetype", "UNKNOWN"),
            "side": trade.get("side", "UNKNOWN"),
            "result": trade.get("result", "UNKNOWN"),
            "realized_pnl": float(trade.get("realized_pnl", trade.get("pnl", 0.0)) or 0.0),
            "r_value": _trade_r_value(trade),
            "balance": equity,
            "drawdown_pct": dd,
        })
    pd.DataFrame(rows).to_csv(equity_path, index=False)

    monthly_items = defaultdict(list)
    for trade in trades or []:
        ts = _safe_parse_ts(trade.get("exit_time") or trade.get("entry_time"))
        month = ts.strftime("%Y-%m") if ts is not None else "UNKNOWN"
        monthly_items[month].append(trade)

    monthly = {}
    for month, items in sorted(monthly_items.items()):
        row = _aggregate_trade_bucket(items)
        balances = [float(t.get("balance_after", t.get("balance", 0.0)) or 0.0) for t in items]
        row["ending_balance"] = round(balances[-1], 6) if balances else 0.0
        monthly[month] = row

    report = {
        "initial_balance": float(initial_balance),
        "final_balance": float(rows[-1]["balance"] if rows else initial_balance),
        "total_trades": len(trades or []),
        "monthly": monthly,
        "files": {"equity_curve_csv": equity_path, "monthly_json": monthly_path},
    }
    os.makedirs(os.path.dirname(monthly_path), exist_ok=True)
    with open(monthly_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def _build_paper_readiness_report(
    *,
    result: dict,
    lifecycle_report: dict,
    archetype_report: dict,
    signal_report: dict | None,
    training_audit: dict,
    wf_folds: list | None,
    output_path: str = "data/paper_readiness_report.json",
) -> dict:
    """Score whether the research stack is ready for paper trading."""
    import json

    reasons = []
    blockers = []
    warnings = []

    trades = int(result.get("total_trades", 0) or 0)
    final_balance = float(result.get("final_balance", INITIAL_BALANCE) or INITIAL_BALANCE)
    net_pct = ((final_balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100.0
    max_dd = float(result.get("max_drawdown", 0.0) or 0.0)
    lifecycle_status = str(lifecycle_report.get("status", "UNKNOWN")) if lifecycle_report else "UNKNOWN"

    min_trades = int(getattr(Config, "PAPER_READY_MIN_TRADES", 30))
    max_dd_allowed = float(getattr(Config, "PAPER_READY_MAX_DD_PCT", 12.0))
    min_net_pct = float(getattr(Config, "PAPER_READY_MIN_NET_PCT", 0.0))
    min_positive_arches = int(getattr(Config, "PAPER_READY_MIN_POSITIVE_ARCHETYPES", 2))
    min_arch_trades = int(getattr(Config, "PAPER_READY_MIN_ARCHETYPE_TRADES", 10))

    if lifecycle_status != "PASS":
        blockers.append(f"Lifecycle audit is {lifecycle_status}, expected PASS.")
    if trades < min_trades:
        warnings.append(f"Closed trades {trades} < paper-ready minimum {min_trades}.")
    if net_pct < min_net_pct:
        blockers.append(f"Net PnL {net_pct:+.2f}% below required {min_net_pct:+.2f}%.")
    if max_dd > max_dd_allowed:
        blockers.append(f"Max drawdown {max_dd:.2f}% exceeds {max_dd_allowed:.2f}%.")

    by_arch = archetype_report.get("by_archetype", {}) if archetype_report else {}
    positive_arches = [
        name for name, row in by_arch.items()
        if int(row.get("trades", 0) or 0) >= min_arch_trades and float(row.get("avg_r", 0.0) or 0.0) > 0.0
    ]
    if len(positive_arches) < min_positive_arches:
        warnings.append(
            f"Only {len(positive_arches)} archetypes have >= {min_arch_trades} trades and positive avgR."
        )

    stability_warnings = archetype_report.get("stability_warnings", []) if archetype_report else []
    if stability_warnings:
        warnings.extend(stability_warnings[:8])

    funnel = signal_report.get("funnel", {}) if signal_report else {}
    meta_acceptance = float(funnel.get("meta_acceptance_rate_pct", 0.0) or 0.0)
    if meta_acceptance > float(getattr(Config, "PAPER_READY_MAX_META_ACCEPTANCE_RATE_PCT", 5.0)):
        warnings.append(f"Meta acceptance {meta_acceptance:.2f}% is high for selective deployment.")

    wf_count = len(wf_folds or [])
    if wf_count < int(getattr(Config, "PAPER_READY_MIN_WF_FOLDS", 20)):
        warnings.append(f"Walk-forward folds {wf_count} below preferred minimum.")

    if str(training_audit.get("training_source", "")).startswith("local"):
        symbol_label = str(getattr(Config, "SYMBOL", "UNKNOWN"))
        warnings.append(f"Training source is local {symbol_label}-derived; multi-asset robustness is not confirmed in this run.")

    if blockers:
        status = "NOT_READY"
    elif trades >= min_trades and len(positive_arches) >= min_positive_arches and not stability_warnings:
        status = "PAPER_READY"
    else:
        status = "RESEARCH_READY"

    timeframe_profile = getattr(Config, "ACTIVE_TIMEFRAME_PROFILE", {}) or {"timeframe": getattr(Config, "TIMEFRAME", "unknown")}

    report = {
        "status": status,
        "symbol": str(getattr(Config, "SYMBOL", "UNKNOWN")),
        "asset_slug": str(getattr(Config, "SYMBOL", "UNKNOWN")).replace("/", "").replace(":", "").lower(),
        "timeframe_profile": timeframe_profile,
        "execution_cost_model": str(getattr(Config, "EXECUTION_COST_MODEL", "base")),
        "net_pnl_pct": round(net_pct, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "closed_trades": trades,
        "positive_archetypes": positive_arches,
        "lifecycle_status": lifecycle_status,
        "training_audit": training_audit,
        "walkforward_folds": wf_count,
        "blockers": blockers,
        "warnings": warnings,
        "reasons": reasons,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


RUNTIME_MARKET_STRUCTURE_COLUMNS = {
    "liquidity_sweep_score", "sweep_low", "sweep_high",
    "volatility_compression", "is_vol_compressed", "is_vol_expanding",
    "htf_1h_return", "htf_4h_return", "htf_1h_trend", "htf_4h_trend",
    "htf_trend_alignment", "volume_z_1d", "range_z_1d",
    "session_asia", "session_london", "session_ny", "session_overlap_london_ny",
    "btc_return_1", "btc_realized_vol_1d", "asset_vs_btc_return_1",
}


def _market_structure_feature_status(df: pd.DataFrame) -> tuple[int, int, float, list[str]]:
    present = sorted(c for c in RUNTIME_MARKET_STRUCTURE_COLUMNS if c in df.columns)
    missing = sorted(c for c in RUNTIME_MARKET_STRUCTURE_COLUMNS if c not in df.columns)
    rate = (len(present) / len(RUNTIME_MARKET_STRUCTURE_COLUMNS) * 100.0) if RUNTIME_MARKET_STRUCTURE_COLUMNS else 0.0
    return len(present), len(missing), rate, missing


def _normalize_runtime_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with datetime column and canonical OHLCV names."""
    work = df.copy()
    if "datetime" not in work.columns:
        work = work.reset_index()
        if "datetime" not in work.columns:
            first_col = work.columns[0]
            work = work.rename(columns={first_col: "datetime"})
    work["datetime"] = pd.to_datetime(work["datetime"], utc=True, errors="coerce")
    if work["datetime"].isna().any():
        raise ValueError("datetime column contains null values after conversion")

    # Keep compatibility with cached files that may use lowercase OHLCV names.
    aliases = {
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    }
    for src, dst in aliases.items():
        if dst not in work.columns and src in work.columns:
            work[dst] = work[src]
    required_ohlcv = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required_ohlcv if c not in work.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns for runtime enrichment: {missing}")
    work = work.sort_values("datetime").reset_index(drop=True)
    return work


def _fallback_market_structure_features(df: pd.DataFrame, reason: str = "") -> pd.DataFrame:
    """Causal pandas-only runtime feature builder used when the full builder is unavailable.

    This fallback intentionally mirrors the core MarketStructureFeatureBuilder features
    needed by the setup engine. It prevents silent degradation to 0% runtime feature
    availability in custom backtest entrypoints that bypass fetch_data().
    """
    try:
        work = _normalize_runtime_ohlcv_frame(df)
        close = pd.to_numeric(work["Close"], errors="coerce")
        high = pd.to_numeric(work["High"], errors="coerce")
        low = pd.to_numeric(work["Low"], errors="coerce")
        volume = pd.to_numeric(work["Volume"], errors="coerce")
        candle_range = (high - low).replace(0, pd.NA).astype(float)
        log_ret = (close / close.shift(1)).apply(lambda x: pd.NA if x is pd.NA or x <= 0 else x)
        import numpy as np
        log_ret = np.log(pd.to_numeric(log_ret, errors="coerce"))

        realized_1d = pd.Series(log_ret).rolling(96, min_periods=20).std() * (96 ** 0.5)
        realized_1w = pd.Series(log_ret).rolling(672, min_periods=100).std() * (672 ** 0.5)
        vol_med = realized_1d.rolling(96, min_periods=20).median().replace(0, pd.NA)
        work["realized_vol_1d_ms"] = realized_1d.fillna(0.0)
        work["realized_vol_1w_ms"] = realized_1w.fillna(0.0)
        work["volatility_compression"] = (realized_1d / vol_med).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        work["is_vol_compressed"] = (work["volatility_compression"] < float(getattr(Config, "SETUP_VOL_COMPRESSION_THRESHOLD", 0.95))).astype(float)
        work["is_vol_expanding"] = (work["volatility_compression"] > 1.25).astype(float)

        work["htf_1h_return"] = close.pct_change(4).fillna(0.0)
        work["htf_4h_return"] = close.pct_change(16).fillna(0.0)
        eps = float(getattr(Config, "SETUP_HTF_RETURN_EPS", 0.0005))
        work["htf_1h_trend"] = np.where(work["htf_1h_return"] > eps, 1.0, np.where(work["htf_1h_return"] < -eps, -1.0, 0.0))
        work["htf_4h_trend"] = np.where(work["htf_4h_return"] > eps, 1.0, np.where(work["htf_4h_return"] < -eps, -1.0, 0.0))
        work["htf_trend_alignment"] = ((work["htf_1h_trend"] == work["htf_4h_trend"]) & (work["htf_1h_trend"] != 0)).astype(float)

        hour = work["datetime"].dt.hour
        work["session_asia"] = ((hour >= 0) & (hour < 8)).astype(float)
        work["session_london"] = ((hour >= 8) & (hour < 16)).astype(float)
        work["session_ny"] = ((hour >= 13) & (hour < 22)).astype(float)
        work["session_overlap_london_ny"] = ((hour >= 13) & (hour < 16)).astype(float)

        prior_high = high.rolling(20, min_periods=5).max().shift(1)
        prior_low = low.rolling(20, min_periods=5).min().shift(1)
        work["sweep_high"] = ((high > prior_high) & (close < prior_high)).astype(float)
        work["sweep_low"] = ((low < prior_low) & (close > prior_low)).astype(float)
        work["liquidity_sweep_score"] = ((work["sweep_high"] + work["sweep_low"]) * (candle_range / close.replace(0, pd.NA))).fillna(0.0)

        def rolling_z(series: pd.Series, window: int = 96) -> pd.Series:
            mean = series.rolling(window, min_periods=max(10, window // 4)).mean()
            std = series.rolling(window, min_periods=max(10, window // 4)).std().replace(0, pd.NA)
            return ((series - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        work["volume_z_1d"] = rolling_z(volume, 96)
        work["range_z_1d"] = rolling_z((candle_range / close.replace(0, pd.NA)).astype(float), 96)
        work["return_1"] = close.pct_change().fillna(0.0)
        # Single-asset BTC runtime: BTC context equals asset context. For non-BTC cached
        # backtests this is still a neutral-safe proxy rather than missing columns.
        work["btc_return_1"] = work["return_1"]
        work["btc_realized_vol_1d"] = work["realized_vol_1d_ms"]
        work["asset_vs_btc_return_1"] = 0.0

        enriched = work.set_index("datetime")
        enriched.index.name = df.index.name or "datetime"
        present, missing_count, rate, missing = _market_structure_feature_status(enriched)
        suffix = f" Fallback reason: {reason}" if reason else ""
        print(
            "  [MarketStructureRuntime] Pandas fallback enrichment applied: "
            f"{present}/{len(RUNTIME_MARKET_STRUCTURE_COLUMNS)} runtime columns available ({rate:.1f}%)." + suffix
        )
        if missing:
            print(f"  [MarketStructureRuntime] Still missing after fallback: {missing[:8]}")
        return enriched
    except Exception as exc:
        print(f"❌ [MarketStructureRuntime] Pandas fallback enrichment failed: {exc}")
        return df


def _ensure_market_structure_features(df: pd.DataFrame, *, strict: bool = False) -> pd.DataFrame:
    """Attach causal market-structure columns to the runtime backtest frame.

    Prompt 28.3 hardens the runtime data path. Custom entrypoints such as
    run_custom_backtest.py may bypass fetch_data(), so enrichment is forced again
    inside run_backtest() and audited loudly instead of silently degrading to
    RANGING_MEAN_REVERSION-only behavior.
    """
    if not bool(getattr(Config, "BACKTEST_MARKET_STRUCTURE_ENRICHMENT", True)):
        print("  [MarketStructureRuntime] Enrichment disabled by Config.BACKTEST_MARKET_STRUCTURE_ENRICHMENT=0.")
        return df

    present, missing_count, rate, missing = _market_structure_feature_status(df)
    if missing_count == 0:
        print(
            "  [MarketStructureRuntime] Runtime frame already enriched: "
            f"{present}/{len(RUNTIME_MARKET_STRUCTURE_COLUMNS)} columns available (100.0%)."
        )
        return df

    print(
        "  [MarketStructureRuntime] Runtime feature audit before enrichment: "
        f"available={present} | missing={missing_count} | rate={rate:.2f}%"
    )

    try:
        import polars as pl
        from core.market_structure_features import MarketStructureFeatureBuilder

        work = _normalize_runtime_ohlcv_frame(df)
        work["asset"] = str(getattr(Config, "SYMBOL", "BTCUSDT")).replace("/", "").upper()

        enriched_pl, report = MarketStructureFeatureBuilder().enrich(
            pl.from_pandas(work),
            external_sources=None,
            write_report=False,
        )
        enriched = enriched_pl.to_pandas()
        enriched["datetime"] = pd.to_datetime(enriched["datetime"], utc=True, errors="coerce")
        enriched = enriched.drop(columns=["asset"], errors="ignore").set_index("datetime")
        enriched.index.name = df.index.name or "datetime"

        present, missing_count, rate, missing = _market_structure_feature_status(enriched)
        print(
            "  [MarketStructureRuntime] Enriched backtest frame: "
            f"available={present} | missing={missing_count} | rate={rate:.2f}%"
        )
        if getattr(report, "warnings", None):
            print(f"  [MarketStructureRuntime] Warnings: {report.warnings[:3]}")
        if missing_count:
            print(f"  [MarketStructureRuntime] Missing after builder: {missing[:8]}")
            enriched = _fallback_market_structure_features(enriched, reason="builder_missing_columns")
        return enriched
    except Exception as exc:
        print(f"⚠️ [MarketStructureRuntime] Builder enrichment failed: {exc}")
        enriched = _fallback_market_structure_features(df, reason=str(exc))
        present, missing_count, rate, missing = _market_structure_feature_status(enriched)
        if strict and missing_count:
            raise RuntimeError(
                "Market-structure runtime enrichment failed strict audit: "
                f"available={present}, missing={missing_count}, missing_cols={missing[:10]}"
            )
        return enriched

# ------------------------------------------------------------------ #
#  FETCH + ANALISI                                                     #
# ------------------------------------------------------------------ #
async def fetch_data() -> pd.DataFrame:
    # Determina i percorsi di cache per il timeframe corrente
    timeframe = Config.TIMEFRAME
    if timeframe == "5m":
        csv_path = os.path.join("data", "btc_5m_10k_cache.csv")
        parquet_path = os.path.join("data", "btc_5m_10k_cache.parquet")
    else:
        csv_path = os.path.join("data", "btc_15m_cache.csv")
        parquet_path = os.path.join("data", "btc_15m_cache.parquet")
        
    # Se il parquet non esiste, ma il csv esiste, avvia la migrazione automatica!
    if not os.path.exists(parquet_path) and os.path.exists(csv_path):
        print(f"📦 [MIGRATION] Rilevato file CSV legacy '{csv_path}'. Avvio migrazione automatica a Parquet...")
        try:
            import polars as pl
            from core.data_collector import DatasetIntegrity, DatasetVersioning
            
            # Leggiamo il CSV con Polars
            df_legacy = pl.read_csv(csv_path)
            
            # Validiamo e ripuliamo i dati
            df_legacy = DatasetIntegrity.detect_and_remove_duplicates(df_legacy)
            df_legacy = DatasetIntegrity.validate_schema(df_legacy, is_features=False)
            df_legacy = DatasetIntegrity.handle_missing_data(df_legacy, max_null_ratio=Config.MAX_NULL_TOLERANCE)
            DatasetIntegrity.validate_timestamps(df_legacy, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
            
            # Scriviamo in formato Parquet con compressione Snappy e metadati
            DatasetVersioning.write_parquet_with_metadata(df_legacy, parquet_path, is_features=False)
            
            # Rimuoviamo il vecchio CSV legacy
            os.remove(csv_path)
            print(f"🗑️ [MIGRATION] File CSV legacy '{csv_path}' eliminato per pulire lo spazio di lavoro.")
        except Exception as e:
            print(f"❌ [MIGRATION ERROR] Impossibile migrare {csv_path} a Parquet: {e}. Fallback su caricamento legacy.")
            
    # Ora carica dal file Parquet se esiste
    if os.path.exists(parquet_path):
        print(f"[INIT] Caricamento dati offline da cache Parquet: {parquet_path}...")
        import polars as pl
        from core.data_collector import DatasetIntegrity
        
        df_pl = pl.read_parquet(parquet_path)
        
        # Validazione finale di integrità prima dell'uso
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
        
        # Converte in Pandas DataFrame per retrocompatibilità
        df = df_pl.to_pandas()
        if "datetime" in df.columns:
            df.set_index("datetime", inplace=True)
            
        print(f"✅ [INTEGRITY CHECK] Dati offline verificati con successo: {len(df)} candele caricate.")
        return _ensure_market_structure_features(TechnicalAnalyzer().add_indicators(df))
        
    # Altrimenti prova a caricare dal vecchio CSV se la migrazione è fallita ma il file esiste ancora
    elif os.path.exists(csv_path):
        print(f"[INIT] Fallback: Caricamento dati offline da cache CSV legacy: {csv_path}...")
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        return _ensure_market_structure_features(TechnicalAnalyzer().add_indicators(df))
        
    else:
        # Nessun file trovato, scarichiamo dati freschi dall'exchange
        print(f"[INIT] Cache non trovata ({parquet_path}). Download in corso via exchange ({Config.SYMBOL} {Config.TIMEFRAME})...")
        from core.client import ExchangeClient
        client = ExchangeClient(
            exchange_id=Config.EXCHANGE_ID,
            symbol=Config.SYMBOL,
            timeframe=Config.TIMEFRAME,
            limit=1000,
        )
        df = await client.fetch_async()
        if df is None or df.empty:
            raise RuntimeError("Fetch fallito: DataFrame vuoto.")
            
        # Validazione e salvataggio dei dati scaricati direttamente in formato Parquet
        import polars as pl
        from core.data_collector import DatasetIntegrity, DatasetVersioning
        
        # Gestiamo l'indice in Pandas e passiamo a Polars
        df_reset = df.reset_index()
        df_pl = pl.DataFrame(df_reset)
        
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        
        DatasetVersioning.write_parquet_with_metadata(df_pl, parquet_path, is_features=False)
        
        return _ensure_market_structure_features(TechnicalAnalyzer().add_indicators(df))


# ------------------------------------------------------------------ #
#  SIMULATORE SINGOLO                                                 #
# ------------------------------------------------------------------ #
def simulate_backtest(
    df: pd.DataFrame, 
    risk_pct: float, 
    max_leverage: float,
    save_charts: bool = False,
    features_df: pd.DataFrame = None,
    wf_folds: list = None
) -> dict:
    engine   = DecisionEngine()  # Inizializzato con i pesi/soglie evoluti di Config
    risk_mgr = DynamicRiskEngine(
        initial_balance=INITIAL_BALANCE,
        vol_lookback=Config.VOL_LOOKBACK,
        dd_caution_pct=Config.DD_CAUTION_PCT,
        dd_reduced_pct=Config.DD_REDUCED_PCT,
        dd_protected_pct=Config.DD_PROTECTED_PCT,
        daily_loss_limit_pct=Config.DAILY_LOSS_LIMIT_PCT,
        profit_lock_pct=Config.PROFIT_LOCK_PCT,
        max_leverage=(
            max_leverage
            if isinstance(max_leverage, (int, float)) and float(max_leverage) > 0
            else getattr(Config, "DYNAMIC_MAX_LEVERAGE", Config.MAX_LEVERAGE)
        ),
    )

    balance       = INITIAL_BALANCE
    trades        = []          # lista dict per ogni trade chiuso
    open_trade    = None        # trade corrente in attesa di SL/TP
    pending_trigger = None      # "Pazienza Strategica" Breakout Trigger
    max_drawdown = 0.0
    peak_balance = INITIAL_BALANCE
    risk_event_warnings = []
    risk_blocked_attempts = 0
    signal_monitor = SignalDensityMonitor(
        meta_prob_threshold=Config.META_PROB_THRESHOLD,
        meta_quality_threshold=Config.META_QUALITY_THRESHOLD,
        output_path=getattr(Config, "SIGNAL_DENSITY_REPORT_PATH", "data/signal_density_report.json"),
        enabled=bool(save_charts and getattr(Config, "SIGNAL_DENSITY_DIAGNOSTICS", True)),
    )

    profiler = get_runtime_profiler(Config)
    sim_profile_enabled = bool(profiler and getattr(profiler, "enabled", False))
    sim_t0 = time.perf_counter()
    sim_acc = {
        "simulation_wf_routing_seconds": 0.0,
        "simulation_open_trade_lifecycle_seconds": 0.0,
        "simulation_pending_trigger_seconds": 0.0,
        "simulation_signal_evaluation_seconds": 0.0,
    }
    sim_counters = {
        "simulation_rows_iterated": 0,
        "wf_model_switches": 0,
        "technical_candidates_seen": 0,
    }

    # Genera i fold walk-forward in caso non siano stati passati
    if wf_folds is None and Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID" and features_df is not None:
        from core.walk_forward import WalkForwardPipeline
        wf_folds = WalkForwardPipeline.get_wf_splits(
            len(df),
            N=getattr(Config, "WF_TRAIN_SIZE", 2000),
            M=getattr(Config, "WF_TEST_SIZE", 500),
            embargo_gap=Config.EMBARGO_GAP,
            train_mode=getattr(Config, "WF_TRAIN_MODE", "rolling"),
            df=df,
            label_horizon=getattr(Config, "WF_LABEL_HORIZON", 100),
            min_train_size=getattr(Config, "WF_MIN_TRAIN_SIZE", 250),
            adaptive=getattr(Config, "WF_AUTO_ADAPTIVE", True),
            min_test_size=getattr(Config, "WF_MIN_TEST_SIZE", 100),
        )

    rows = df.reset_index()  # iteriamo per indice intero

    # Prompt 28.8.3: vectorized WF routing + fast evaluation-only state cache.
    # The previous implementation still called ensure_wf_model() on fold switches.
    # In evaluation-only mode that method rebuilds local fold datasets only to
    # produce audit metadata, which dominated 5m runs.  Here we precompute an
    # int fold-key array and pre-register fold states from split metadata, so the
    # candidate loop only performs an O(1) array lookup and a cheap model switch
    # when the fold id changes.
    import numpy as _np

    active_fold_key_by_index = None
    fast_eval_only_wf_cache = bool(
        Config.AI_ENABLED
        and Config.STRATEGY_MODE == "AI_HYBRID"
        and features_df is not None
        and wf_folds
        and bool(getattr(Config, "WF_EVALUATION_ONLY", True))
        and not bool(getattr(Config, "WF_ALLOW_LOCAL_RETRAIN", False))
        and bool(getattr(Config, "WF_FAST_EVAL_ONLY_ROUTING_CACHE", True))
    )
    ai_router = TradingAI() if (Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID") else None
    current_active_fold_key = object()

    if Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID" and features_df is not None and wf_folds:
        active_fold_key_by_index = _np.full(len(rows), -1, dtype=_np.int64)

        if fast_eval_only_wf_cache and ai_router is not None:
            # Snapshot once.  The model registry is global in eval-only mode;
            # fold boundaries are retained for reporting/source diagnostics.
            registered = 0
            for fold in wf_folds:
                fold_key = int(getattr(fold, "test_start", -1))
                start = max(1, int(getattr(fold, "test_start", 0)))
                end = min(len(rows) - 1, int(getattr(fold, "test_end", -1)))
                if end >= start and fold_key >= 0:
                    active_fold_key_by_index[start:end + 1] = fold_key

                if fold_key >= 0 and fold_key not in getattr(ai_router, "_wf_models", {}):
                    try:
                        ai_router._wf_models[fold_key] = ai_router._snapshot_current_manager_state(
                            train_start=int(getattr(fold, "train_start", 0)),
                            train_end=int(getattr(fold, "train_end", 0)),
                            embargo_start=int(getattr(fold, "embargo_start", 0)),
                            embargo_end=int(getattr(fold, "embargo_end", 0)),
                            test_start=int(getattr(fold, "test_start", 0)),
                            test_end=int(getattr(fold, "test_end", 0)),
                            num_purged_samples=int(getattr(fold, "num_purged_samples", 0)),
                            effective_train_size=int(getattr(fold, "effective_train_size", 0)),
                            effective_test_size=int(getattr(fold, "effective_test_size", 0)),
                            evaluation_only=True,
                            evaluation_reason="fast_eval_only_routing_cache",
                        )
                        registered += 1
                    except Exception:
                        # Fall back to the conservative ensure_wf_model path below
                        # if the singleton internals are unavailable.
                        fast_eval_only_wf_cache = False
            if profiler:
                profiler.add_counter("wf_fast_eval_only_cache_enabled", bool(fast_eval_only_wf_cache))
                profiler.add_counter("wf_fast_eval_only_states_registered", registered)
        else:
            for fold in wf_folds:
                fold_key = int(getattr(fold, "test_start", -1))
                start = max(1, int(getattr(fold, "test_start", 0)))
                end = min(len(rows) - 1, int(getattr(fold, "test_end", -1)))
                if end >= start and fold_key >= 0:
                    active_fold_key_by_index[start:end + 1] = fold_key

        if profiler:
            profiler.add_counter("wf_fold_membership_precomputed", True)
            profiler.add_counter("wf_folds_available", len(wf_folds or []))
            profiler.add_counter("wf_routing_array_dtype", str(getattr(active_fold_key_by_index, "dtype", "none")))

    for i in range(1, len(rows)):
        row = rows.iloc[i]
        signal_monitor.observe_bar()
        active_fold = None

        # Walk-Forward AI Update
        if Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID" and features_df is not None and wf_folds:
            _wf_t0 = time.perf_counter() if sim_profile_enabled else None
            fold_key = int(active_fold_key_by_index[i]) if active_fold_key_by_index is not None and i < len(active_fold_key_by_index) else -1
            active_model_key = None if fold_key < 0 else fold_key
            if active_model_key != current_active_fold_key:
                if ai_router is None:
                    ai_router = TradingAI()
                if active_model_key is None:
                    ai_router.set_active_model(None)
                else:
                    if not fast_eval_only_wf_cache:
                        # Conservative fallback: only used when local retraining is
                        # enabled or the fast eval-only snapshot cache is disabled.
                        active_fold = next((f for f in wf_folds if int(getattr(f, "test_start", -1)) == active_model_key), None)
                        if active_fold is not None:
                            ai_router.ensure_wf_model(df, features_df, active_fold)
                    ai_router.set_active_model(active_model_key)
                current_active_fold_key = active_model_key
                sim_counters["wf_model_switches"] += 1
            if sim_profile_enabled:
                sim_acc["simulation_wf_routing_seconds"] += time.perf_counter() - _wf_t0

        sim_counters["simulation_rows_iterated"] += 1

        # 1. Gestione trade aperto: cerca SL o TP nelle candele successive
        _open_t0 = time.perf_counter() if sim_profile_enabled else None
        if open_trade is not None:
            hi  = float(row["High"])
            lo  = float(row["Low"])
            sl  = open_trade["sl"]
            entry     = open_trade["entry"]
            size      = open_trade["size"]
            side      = open_trade["side"]
            atr_val   = open_trade.get("atr_val", 0.0)
            be_trig   = open_trade.get("be_triggered", False)

            # Protezione Capitale: Sposta SL a BE se profitto raggiunge 1x ATR
            if atr_val > 0.0 and not be_trig:
                if side == "BUY" and hi >= entry + atr_val:
                    open_trade["be_triggered"] = True
                    open_trade["sl"] = entry
                    sl = entry
                elif side == "SELL" and lo <= entry - atr_val:
                    open_trade["be_triggered"] = True
                    open_trade["sl"] = entry
                    sl = entry

            if Config.USE_SCALE_OUT:
                # ── SCALE-OUT MODE (50/50 split) ──
                tp1       = open_trade["tp1"]
                tp2       = open_trade["tp2"]
                tp1_hit   = open_trade.get("tp1_hit", False)

                # Check per TP1
                if not tp1_hit:
                    hit_tp1 = (side == "BUY" and hi >= tp1) or (side == "SELL" and lo <= tp1)
                    hit_sl = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                    if hit_tp1:
                        open_trade["tp1_hit"] = True
                        tp1_hit = True
                        pnl_1 = (size / 2) * (tp1 - entry) if side == "BUY" else (size / 2) * (entry - tp1)
                        comm_1, cost_detail_1 = _execution_cost_for_trade(
                            size=(size / 2), entry_price=entry, exit_price=tp1, side=side,
                            atr_val=atr_val, atr_pct=open_trade.get("atr_pct", 0.0),
                            vol_regime=open_trade.get("regime", "NORMAL"), order_type="LIMIT", entry_type=open_trade.get("entry_type", "BREAKOUT")
                        )
                        open_trade["execution_cost_total"] = float(open_trade.get("execution_cost_total", 0.0) or 0.0) + float(comm_1)
                        open_trade.setdefault("execution_cost_details", []).append(cost_detail_1)
                        open_trade["execution_cost_bps"] = float(cost_detail_1.get("total_round_trip_cost_bps", 0.0) or 0.0)
                        net_pnl_1 = pnl_1 - comm_1
                        balance += net_pnl_1
                        open_trade["pnl_tp1_net"] = net_pnl_1

                        if Config.USE_BREAKEVEN_ON_TP1:
                            new_sl = entry + (2 * entry * COMMISSION_RATE) if side == "BUY" else entry - (2 * entry * COMMISSION_RATE)
                            sl = new_sl
                            open_trade["sl"] = sl
                            open_trade["be_triggered"] = True
                    elif hit_sl:
                        pnl = size * (sl - entry) if side == "BUY" else size * (entry - sl)
                        commission, cost_detail = _execution_cost_for_trade(
                            size=size, entry_price=entry, exit_price=sl, side=side,
                            atr_val=atr_val, atr_pct=open_trade.get("atr_pct", 0.0),
                            vol_regime=open_trade.get("regime", "NORMAL"), order_type="STOP", entry_type=open_trade.get("entry_type", "BREAKOUT")
                        )
                        open_trade["execution_cost_total"] = float(open_trade.get("execution_cost_total", 0.0) or 0.0) + float(commission)
                        open_trade.setdefault("execution_cost_details", []).append(cost_detail)
                        open_trade["execution_cost_bps"] = float(cost_detail.get("total_round_trip_cost_bps", 0.0) or 0.0)
                        net_pnl = pnl - commission
                        balance_before = balance
                        balance += net_pnl
                        peak_balance, max_drawdown, _closed_trade = _apply_trade_close(
                            trades=trades,
                            risk_mgr=risk_mgr,
                            df=df,
                            row=row,
                            open_trade=open_trade,
                            result="LOSS",
                            realized_pnl=net_pnl,
                            balance_before=balance_before,
                            balance_after=balance,
                            peak_balance=peak_balance,
                            max_drawdown=max_drawdown,
                            save_charts=save_charts,
                            sl_for_report=open_trade["initial_sl"],
                            tp_for_report=tp2,
                        )

                        open_trade = None
                        if balance <= 0: break

                if open_trade is not None and open_trade.get("tp1_hit", False):
                    hit_tp2 = (side == "BUY" and hi >= tp2) or (side == "SELL" and lo <= tp2)
                    hit_sl2 = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                    if hit_tp2 or hit_sl2:
                        if hit_tp2 and not hit_sl2:
                            exit_price_2 = tp2
                            result = "WIN"
                        else:
                            exit_price_2 = sl
                            result = "WIN_PARTIAL"

                        pnl_2 = (size / 2) * (exit_price_2 - entry) if side == "BUY" else (size / 2) * (entry - exit_price_2)
                        comm_2, cost_detail_2 = _execution_cost_for_trade(
                            size=(size / 2), entry_price=entry, exit_price=exit_price_2, side=side,
                            atr_val=atr_val, atr_pct=open_trade.get("atr_pct", 0.0),
                            vol_regime=open_trade.get("regime", "NORMAL"), order_type=("LIMIT" if hit_tp2 and not hit_sl2 else "STOP"), entry_type=open_trade.get("entry_type", "BREAKOUT")
                        )
                        open_trade["execution_cost_total"] = float(open_trade.get("execution_cost_total", 0.0) or 0.0) + float(comm_2)
                        open_trade.setdefault("execution_cost_details", []).append(cost_detail_2)
                        open_trade["execution_cost_bps"] = float(cost_detail_2.get("total_round_trip_cost_bps", 0.0) or 0.0)
                        net_pnl_2 = pnl_2 - comm_2
                        net_pnl_total = open_trade["pnl_tp1_net"] + net_pnl_2
                        balance_before = balance - open_trade["pnl_tp1_net"]
                        balance += net_pnl_2

                        peak_balance, max_drawdown, _closed_trade = _apply_trade_close(
                            trades=trades,
                            risk_mgr=risk_mgr,
                            df=df,
                            row=row,
                            open_trade=open_trade,
                            result=result,
                            realized_pnl=net_pnl_total,
                            balance_before=balance_before,
                            balance_after=balance,
                            peak_balance=peak_balance,
                            max_drawdown=max_drawdown,
                            save_charts=save_charts,
                            sl_for_report=sl,
                            tp_for_report=tp2,
                        )

                        open_trade = None
                        if balance <= 0: break

            else:
                # ── SINGLE TARGET MODE (SL / TP diretto) ──
                tp = open_trade["tp"]
                hit_tp = (side == "BUY" and hi >= tp) or (side == "SELL" and lo <= tp)
                hit_sl = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                if hit_tp and not hit_sl:
                    pnl = size * (tp - entry) if side == "BUY" else size * (entry - tp)
                    commission, cost_detail = _execution_cost_for_trade(
                        size=size, entry_price=entry, exit_price=tp, side=side,
                        atr_val=atr_val, atr_pct=open_trade.get("atr_pct", 0.0),
                        vol_regime=open_trade.get("regime", "NORMAL"), order_type="LIMIT", entry_type=open_trade.get("entry_type", "BREAKOUT")
                    )
                    open_trade["execution_cost_total"] = float(open_trade.get("execution_cost_total", 0.0) or 0.0) + float(commission)
                    open_trade.setdefault("execution_cost_details", []).append(cost_detail)
                    open_trade["execution_cost_bps"] = float(cost_detail.get("total_round_trip_cost_bps", 0.0) or 0.0)
                    net_pnl = pnl - commission
                    balance += net_pnl
                    result = "WIN"
                elif hit_sl:
                    pnl = size * (sl - entry) if side == "BUY" else size * (entry - sl)
                    commission, cost_detail = _execution_cost_for_trade(
                        size=size, entry_price=entry, exit_price=sl, side=side,
                        atr_val=atr_val, atr_pct=open_trade.get("atr_pct", 0.0),
                        vol_regime=open_trade.get("regime", "NORMAL"), order_type="STOP", entry_type=open_trade.get("entry_type", "BREAKOUT")
                    )
                    open_trade["execution_cost_total"] = float(open_trade.get("execution_cost_total", 0.0) or 0.0) + float(commission)
                    open_trade.setdefault("execution_cost_details", []).append(cost_detail)
                    open_trade["execution_cost_bps"] = float(cost_detail.get("total_round_trip_cost_bps", 0.0) or 0.0)
                    net_pnl = pnl - commission
                    balance += net_pnl
                    result = "BREAKEVEN" if open_trade.get("be_triggered", False) else "LOSS"
                else:
                    net_pnl = None

                if net_pnl is not None:
                    balance_before = balance - net_pnl
                    peak_balance, max_drawdown, _closed_trade = _apply_trade_close(
                        trades=trades,
                        risk_mgr=risk_mgr,
                        df=df,
                        row=row,
                        open_trade=open_trade,
                        result=result,
                        realized_pnl=net_pnl,
                        balance_before=balance_before,
                        balance_after=balance,
                        peak_balance=peak_balance,
                        max_drawdown=max_drawdown,
                        save_charts=save_charts,
                        sl_for_report=sl,
                        tp_for_report=tp,
                    )

                    open_trade = None
                    if balance <= 0: break

            # Se il trade è ancora aperto (nessun target della seconda metà è stato colpito)
            if open_trade is not None:
                # Invecchia il trigger breakout se pendente
                if pending_trigger is not None:
                    pending_trigger["ttl"] -= 1
                    if pending_trigger["ttl"] <= 0:
                        pending_trigger = None
                continue

        if sim_profile_enabled and _open_t0 is not None:
            sim_acc["simulation_open_trade_lifecycle_seconds"] += time.perf_counter() - _open_t0

        # 2. Gestione breakout trigger pendente (solo se non c'è una posizione aperta)
        _pending_t0 = time.perf_counter() if sim_profile_enabled else None
        if open_trade is None and pending_trigger is not None:
            hi = float(row["High"])
            lo = float(row["Low"])
            side = pending_trigger["side"]
            sh = pending_trigger["signal_high"]
            sl_level = pending_trigger["signal_low"]
            
            triggered = False
            entry_price = 0.0
            
            if side == "BUY" and hi >= sh:
                triggered = True
                entry_price = max(float(row["Open"]), sh)
            elif side == "SELL" and lo <= sl_level:
                triggered = True
                entry_price = min(float(row["Open"]), sl_level)
                
            if triggered:
                signal_monitor.observe_pending_filled()
                # Eseguiamo il trade!
                # Calcoliamo i parametri di rischio del trade usando entry_price effettivo
                atr_val = pending_trigger["atr_val"]
                current_rr = pending_trigger["current_rr"]
                targets = risk_mgr.calculate_targets(side, entry_price, atr_val, rr_ratio=current_rr)
                sl, tp  = targets["sl"], targets["tp"]
                
                risk_per_unit = abs(entry_price - sl)
                if risk_per_unit > 0:
                    risk_pct = pending_trigger["risk_pct"]
                    max_leverage = pending_trigger["max_leverage"]
                    regime = pending_trigger["regime"]
                    ai_prob = pending_trigger.get("ai_prob", 50.0)
                    
                    # Sizing dinamico o Kelly Criterion se attivo.
                    # IMPORTANT: route all sizing through DynamicRiskEngine.size_position()
                    # so risk diagnostics, volatility multipliers, drawdown tiers and effective
                    # leverage are recorded for every opened trade.  The previous implementation
                    # mutated balance directly later in the loop while never creating risk snapshots,
                    # producing the invalid dashboard symptom: "Trades analysed : 0".
                    is_dynamic_profile = risk_pct == "DYNAMIC"
                    if Config.USE_KELLY_SIZING and ai_prob != 50.0:
                        # For the DYNAMIC profile, Kelly is an input to risk sizing,
                        # not permission to bet 15-20% of equity.  The previous
                        # implementation used 15% as the default Kelly fallback,
                        # causing a single losing trade to breach the daily loss
                        # limit and block the rest of the backtest.
                        risk_pct_base = (
                            getattr(Config, "DYNAMIC_DEFAULT_RISK_PCT", Config.RISK_PER_TRADE)
                            if is_dynamic_profile
                            else risk_pct
                        )
                        current_risk = risk_mgr.calculate_kelly_risk_pct(ai_prob, current_rr, risk_pct_base)
                    elif is_dynamic_profile:
                        thresh = Config.TRENDING_THRESHOLD if regime == "TRENDING" else Config.RANGING_THRESHOLD
                        margin_above = abs(pending_trigger["score"]) - thresh
                        current_risk = 0.03 if margin_above >= 15 else getattr(Config, "DYNAMIC_DEFAULT_RISK_PCT", Config.RISK_PER_TRADE)
                    else:
                        current_risk = float(risk_pct)

                    if is_dynamic_profile:
                        current_risk = min(
                            float(current_risk),
                            float(getattr(Config, "DYNAMIC_MAX_RISK_PCT", 0.03)),
                        )

                    size, risk_snapshot = risk_mgr.size_position(
                        balance=balance,
                        entry_price=entry_price,
                        sl_price=sl,
                        side=side,
                        regime=regime,
                        ai_prob=ai_prob,
                        rr_ratio=current_rr,
                        atr_val=atr_val,
                        base_risk_pct=current_risk,
                        commission=COMMISSION_RATE,
                    )

                    # If the risk engine blocks a trade (daily loss limit / circuit breaker)
                    # or returns zero size, do NOT create a zero-PnL synthetic trade.
                    # The previous implementation still opened such positions, which made
                    # the selected-profile report show fake WIN/LOSS trades with PnL 0.0000
                    # while the dashboard counted only the one risk-bearing trade.
                    if getattr(risk_snapshot, "daily_loss_blocked", False) or size <= 0:
                        risk_blocked_attempts += 1
                        signal_monitor.observe_risk_blocked()
                        pending_trigger = None
                        continue
                    
                    # Estrai indicatori della candela di segnale per l'analisi del regime
                    from core.data_collector import DataCollector
                    last_window = pending_trigger["window_df"]
                    last_row = last_window.iloc[-1]
                    close_val = float(last_row.get("Close", last_row.get("close", 0.0)))
                    ema_200_val = float(last_row.get("ema_200", 0.0))
                    close_vs_ema = ((close_val - ema_200_val) / ema_200_val * 100) if ema_200_val > 0 else 0.0
                    atr_val = float(last_row.get("atr", atr_val))
                    atr_pct = (atr_val / close_val * 100) if close_val > 0 else 0.0
                    
                    # Calcola volume ratio
                    volume_ratio = 1.0
                    if len(last_window) >= 20:
                        vol_mean = last_window.iloc[-20:]["Volume"].mean()
                        if vol_mean > 0:
                            volume_ratio = float(last_row["Volume"]) / vol_mean
                            
                    # Calcola setup quality score tramite SetupFilter
                    from core.setup_filter import SetupFilter
                    setup_quality = SetupFilter.calculate_quality_score(last_row, volume_ratio, side)
                    
                    open_trade = {
                        "side": side,
                        "type": "BREAKOUT",
                        "entry": entry_price,
                        "sl": sl,
                        "initial_sl": sl,
                        "be_triggered": False,
                        "tp": tp,
                        "tp1": targets["tp1"],
                        "tp2": targets["tp2"],
                        "tp1_hit": False,
                        "pnl_tp1_net": 0.0,
                        "size": size,
                        "risk_snapshot_trade_num": getattr(risk_snapshot, "trade_num", None),
                        "risk_snapshot_pct": getattr(risk_snapshot, "final_risk_pct", current_risk),
                        "effective_leverage": getattr(risk_snapshot, "effective_leverage", 0.0),
                        "window_df": pending_trigger["window_df"],
                        "active_conf": pending_trigger["active_conf"],
                        "confluence_comb": pending_trigger["confluence_comb"],
                        "ai_prob": ai_prob,
                        "atr_val": atr_val,
                        "entry_type": str(pending_trigger.get("entry_type", "BREAKOUT")),
                        "execution_cost_model": str(getattr(Config, "EXECUTION_COST_MODEL", "base")),
                        "execution_cost_total": 0.0,
                        "execution_cost_bps": 0.0,
                        "execution_cost_details": [],
                        
                        # --- regime performance analytics metadata ---
                        "entry_time": str(row["datetime"]) if "datetime" in row else str(row.name),
                        "regime": regime,
                        "adx": float(last_row.get("adx", 0.0)),
                        "atr_pct": float(last_row.get("atr_pct", atr_pct)),
                        "volume": float(last_row.get("Volume", last_row.get("volume", 0.0))),
                        "volume_ratio": volume_ratio,
                        "close_vs_ema": close_vs_ema,
                        "setup_quality": setup_quality,
                        "setup_archetype": pending_trigger.get("setup_archetype", "UNKNOWN"),
                        "structure_score": pending_trigger.get("structure_score", 0.0),
                        "edge_adjustment_r": pending_trigger.get("edge_adjustment_r", 0.0),
                        "archetype_gate": pending_trigger.get("archetype_gate", {}),
                    }
                    signal_monitor.observe_opened_trade()
                pending_trigger = None
            else:
                # Decrementa il TTL del breakout trigger
                pending_trigger["ttl"] -= 1
                if pending_trigger["ttl"] <= 0:
                    signal_monitor.observe_pending_expired()
                    pending_trigger = None  # Scaduto: falso breakout scartato!

        if sim_profile_enabled and _pending_t0 is not None:
            sim_acc["simulation_pending_trigger_seconds"] += time.perf_counter() - _pending_t0

        # 3. Valuta nuovi segnali
        _signal_t0 = time.perf_counter() if sim_profile_enabled else None
        if open_trade is None and pending_trigger is None:
            window   = df.iloc[:i]
            last     = window.iloc[-1]
            
            if Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID":
                # Stage 1: Rules-based Technical Signal Candidate
                tech_verdict, tech_score, conf, entry_type, conf_verdict, conf_comb = engine._evaluate_score(window)
                
                if tech_verdict in ("BUY", "SELL") and entry_type is not None:
                    signal_monitor.observe_technical_candidate(side=tech_verdict, tech_score=tech_score, entry_type=entry_type)
                    sim_counters["technical_candidates_seen"] += 1
                    # Stage 2: Technical Setup Filter & Quality Scoring
                    from core.data_collector import DataCollector
                    from core.setup_filter import SetupFilter
                    
                    features = DataCollector.extract_features(window, len(window) - 1)
                    volume_ratio = features.get("volume_ratio", 1.0)
                    is_tech_ok, setup_details = SetupFilter.evaluate_setup_details(tech_verdict, last, volume_ratio)
                    setup_quality = float(setup_details.get("setup_quality", 0.0))
                    structure_score = float(setup_details.get("structure_score", 0.0))
                    setup_archetype = str(setup_details.get("setup_archetype", "UNKNOWN"))
                    edge_adjustment_r = float(setup_details.get("edge_adjustment_r", 0.0))
                    features["setup_quality"] = setup_quality
                    features["structure_score"] = structure_score
                    features["setup_archetype"] = setup_archetype
                    
                    # Stage 2: Meta-Model prediction & Calibration (dual-regime routed)
                    ai = TradingAI()
                    ai_ready_for_prediction = bool(ai.is_ready())
                    if ai_ready_for_prediction:
                        p_cal = ai.predict_probability(features, side=tech_verdict)
                        prediction_source = str(getattr(ai, "_active_model_source", "GLOBAL"))
                    else:
                        p_cal = 50.0
                        prediction_source = "NOT_READY_FALLBACK_50"
                    ai_diagnostics = _ai_prediction_diagnostics(
                        ai,
                        features,
                        active_fold=active_fold,
                        p_cal=p_cal,
                        prediction_source=prediction_source,
                    )
                        
                    # Stage 2: Expected Value setup ranking & prioritization
                    from core.setup_ranker import SetupRanker
                    candidate = {
                        "side": tech_verdict,
                        "p_cal": p_cal,
                        "rr": Config.TRENDING_RR if last.get("market_regime", "RANGING") == "TRENDING" else Config.RANGING_RR,
                        "setup_quality": setup_quality
                    }
                    
                    ranked = SetupRanker.rank_candidates([candidate], available_slots=1)
                    expected_value = SetupRanker.calculate_expected_value(p_cal, candidate["rr"])

                    # Cost-aware meta-labeling diagnostic: gross EV can look positive
                    # while net EV disappears after expected execution friction.  This
                    # is diagnostic-only by default; enable META_COST_AWARE_GATING=1
                    # only after validating threshold recommendations out-of-sample.
                    close_price = float(last.get("Close", last.get("close", 0.0)) or 0.0)
                    atr_for_cost = float(last.get("atr", features.get("atr", 0.0)) or 0.0)
                    atr_pct_for_cost = float(last.get("atr_pct", features.get("atr_pct", 0.0)) or 0.0)
                    atr_ratio_for_cost = 1.0
                    try:
                        if len(window) >= Config.VOL_LOOKBACK and "atr" in window.columns:
                            atr_med = float(window["atr"].tail(Config.VOL_LOOKBACK).median())
                            atr_ratio_for_cost = (atr_for_cost / atr_med) if atr_med > 0 else 1.0
                    except Exception:
                        atr_ratio_for_cost = 1.0
                    cost_estimate = CostAwareMetaLabeler.estimate(
                        probability=p_cal,
                        rr_ratio=candidate["rr"],
                        entry_price=close_price,
                        stop_loss=None,
                        atr_val=atr_for_cost,
                        atr_ratio=atr_ratio_for_cost,
                        atr_pct=atr_pct_for_cost,
                        vol_regime=None,
                        order_type="LIMIT",
                        entry_type=str(entry_type or "BREAKOUT"),
                    )

                    # Prompt 27: market-structure setup refactor.  Structure quality
                    # is diagnostic by default and contributes a small expected-edge
                    # adjustment so liquidity/HTF/session-confirmed setups are not
                    # treated identically to local indicator-only setups.
                    if edge_adjustment_r:
                        from dataclasses import replace

                        adjusted_net_edge_r = (
                            float(cost_estimate.expected_net_edge_r)
                            + float(edge_adjustment_r)
                        )

                        adjusted_accepted_cost_aware = bool(
                            adjusted_net_edge_r >= float(
                                getattr(Config, "META_MIN_NET_EDGE_R", 0.0)
                            )
                            and float(cost_estimate.cost_to_edge_ratio) <= float(
                                getattr(Config, "META_MAX_COST_TO_EDGE_RATIO", 1.0)
                            )
                        )

                        cost_estimate = replace(
                            cost_estimate,
                            expected_net_edge_r=adjusted_net_edge_r,
                            accepted_cost_aware=adjusted_accepted_cost_aware,
                        )

                    meta_accepted_gross = bool(ranked and p_cal >= Config.META_PROB_THRESHOLD and is_tech_ok)
                    cost_gate_ok = bool(
                        not getattr(Config, "META_COST_AWARE_GATING", False)
                        or cost_estimate.accepted_cost_aware
                    )
                    archetype_gate_ok, archetype_rejection_reason, archetype_gate_details = _passes_archetype_gate(
                        archetype=setup_archetype,
                        p_cal=p_cal,
                        setup_quality=setup_quality,
                        structure_score=structure_score,
                        expected_net_edge_r=float(cost_estimate.expected_net_edge_r),
                    )
                    archetype_disabled_reason = _archetype_block_reason(setup_archetype)
                    archetype_enabled_ok = not bool(archetype_disabled_reason)
                    final_rejection_reason = archetype_disabled_reason or archetype_rejection_reason
                    meta_accepted = bool(meta_accepted_gross and cost_gate_ok and archetype_gate_ok and archetype_enabled_ok)

                    structure_components_for_report = dict(setup_details.get("structure_components", {}) or {})
                    if archetype_gate_details:
                        for gate_name, gate_val in archetype_gate_details.get("gates", {}).items():
                            structure_components_for_report[f"gate_{gate_name}"] = float(gate_val)
                        for check_name, check_ok in archetype_gate_details.get("checks", {}).items():
                            structure_components_for_report[f"gate_pass_{check_name}"] = float(bool(check_ok))

                    signal_monitor.observe_meta_decision(
                        side=tech_verdict,
                        p_cal=p_cal,
                        setup_quality=setup_quality,
                        tech_score=tech_score,
                        expected_value=expected_value,
                        expected_net_edge=cost_estimate.expected_net_edge_r,
                        expected_round_trip_cost_bps=cost_estimate.expected_round_trip_cost_bps,
                        cost_to_edge_ratio=cost_estimate.cost_to_edge_ratio,
                        cost_aware_accepted=cost_estimate.accepted_cost_aware,
                        is_tech_ok=is_tech_ok,
                        ranked=bool(ranked),
                        accepted=meta_accepted,
                        regime=str(last.get("market_regime", "RANGING")),
                        setup_archetype=setup_archetype,
                        structure_score=structure_score,
                        edge_adjustment_r=edge_adjustment_r,
                        structure_components=structure_components_for_report,
                        structure_reasons=setup_details.get("structure_reasons", []),
                        rejection_reason=final_rejection_reason,
                        ai_diagnostics=ai_diagnostics,
                    )
                    
                    # Gating: setup must pass global meta, cost-aware and archetype-specific thresholds.
                    if meta_accepted:
                        verdict = tech_verdict
                        score = int(tech_score * (1.0 - Config.AI_WEIGHT) + (p_cal - 50.0) * 2.0 * Config.AI_WEIGHT)
                        active_conf = {
                            "ai_prob": p_cal,
                            "setup_quality": setup_quality,
                            "tech_score": tech_score,
                            "setup_archetype": setup_archetype,
                            "structure_score": structure_score,
                            "edge_adjustment_r": edge_adjustment_r,
                            "archetype_gate": archetype_gate_details.get("gates", {}),
                        }
                        confluence_comb = f"{conf_comb}+Meta_OK(p:{p_cal:.1f}%,q:{setup_quality:.1f},netEV:{cost_estimate.expected_net_edge_r:.3f}R)"
                    else:
                        verdict = "HOLD"
                        entry_type = None
                        score = 0
                        active_conf = {"ai_prob": p_cal, "setup_quality": setup_quality, "tech_score": tech_score, "setup_archetype": setup_archetype, "structure_score": structure_score, "edge_adjustment_r": edge_adjustment_r, "archetype_gate": archetype_gate_details.get("gates", {})}
                        confluence_comb = f"Meta_Filtered(p:{p_cal:.1f}%,q:{setup_quality:.1f},s:{structure_score:.1f},netEV:{cost_estimate.expected_net_edge_r:.3f}R,reason:{final_rejection_reason or 'global_gate'})"
                else:
                    signal_monitor.observe_no_technical_candidate()
                    verdict = "HOLD"
                    entry_type = None
                    score = 0
                    active_conf = {"ai_prob": 50.0, "setup_quality": 0.0, "tech_score": tech_score}
                    confluence_comb = "None"
            else:
                res = engine.evaluate(window)
                if len(res) == 6:
                    verdict, score, active_conf, entry_type, confluence_verdict, confluence_comb = res
                else:
                    verdict, score, active_conf, entry_type = res
                    confluence_verdict = "GREEN" if verdict in ("BUY", "SELL") else "RED"
                    confluence_comb = "Legacy"

            if verdict not in ("BUY", "SELL") or entry_type is None:
                continue

            close_p = float(last["Close"])
            atr_val = float(last["atr"]) if float(last["atr"]) > 0 else close_p * 0.01

            # R:R dinamico basato sul Regime di Mercato attuale
            regime = last.get("market_regime", "RANGING")
            current_rr = Config.TRENDING_RR if regime == "TRENDING" else Config.RANGING_RR

            ai_prob = active_conf.get("ai_prob", 50.0)

            if bool(getattr(Config, "PRE_RISK_THROTTLE_ON_DAILY_BLOCK", True)):
                try:
                    if risk_mgr._check_daily_loss_limit():
                        signal_monitor.observe_risk_blocked()
                        continue
                except Exception:
                    pass

            signal_monitor.observe_pending_created()
            pending_trigger = {
                "side": verdict,
                "signal_high": float(last["High"]),
                "signal_low": float(last["Low"]),
                "ttl": 1, # Attendi al massimo 1 candela per il breakout (scalping)
                "atr_val": atr_val,
                "current_rr": current_rr,
                "score": score,
                "confluence_comb": confluence_comb,
                "active_conf": active_conf,
                "window_df": window.copy(),
                "risk_pct": risk_pct,
                "max_leverage": max_leverage,
                "regime": regime,
                "ai_prob": ai_prob,
                "setup_archetype": active_conf.get("setup_archetype", "UNKNOWN"),
                "structure_score": active_conf.get("structure_score", 0.0),
                "edge_adjustment_r": active_conf.get("edge_adjustment_r", 0.0),
                "archetype_gate": active_conf.get("archetype_gate", {})
            }
        if sim_profile_enabled and _signal_t0 is not None:
            sim_acc["simulation_signal_evaluation_seconds"] += time.perf_counter() - _signal_t0

    if profiler:
        for _phase_name, _seconds in sim_acc.items():
            profiler.phases[_phase_name] = profiler.phases.get(_phase_name, 0.0) + float(_seconds)
        profiler.phases["simulation_candidate_loop_seconds"] = profiler.phases.get("simulation_candidate_loop_seconds", 0.0) + (time.perf_counter() - sim_t0)
        for _counter_name, _value in sim_counters.items():
            profiler.add_counter(_counter_name, _value)

    wins = len([t for t in trades if t["result"] == "WIN"])
    partial_wins = len([t for t in trades if t["result"] == "WIN_PARTIAL"])
    losses = len([t for t in trades if t["result"] == "LOSS"])
    breakevens = len([t for t in trades if t["result"] == "BREAKEVEN"])
    
    total_wins = wins + partial_wins
    trade_con_esito = total_wins + losses
    win_rate = (total_wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0

    risk_events = len(getattr(risk_mgr, "trade_events", []))
    risk_snapshots = len(risk_mgr.risk_log)
    risk_bearing_snapshots = sum(
        1 for snap in risk_mgr.risk_log
        if not getattr(snap, "daily_loss_blocked", False)
        and float(getattr(snap, "position_size", 0.0) or 0.0) > 0.0
        and float(getattr(snap, "risk_capital", 0.0) or 0.0) > 0.0
    )
    if len(trades) != risk_events:
        risk_event_warnings.append(
            f"Closed trades ({len(trades)}) != risk trade events ({risk_events})."
        )
    if len(trades) != risk_bearing_snapshots:
        risk_event_warnings.append(
            f"Closed trades ({len(trades)}) != executable risk sizing snapshots ({risk_bearing_snapshots})."
        )

    signal_monitor.closed_trades = len(trades)
    signal_density_report = signal_monitor.export() if signal_monitor.enabled else None

    return {
        "final_balance": balance,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "total_trades": len(trades),
        "wins": wins,
        "partial_wins": partial_wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "risk_diagnostics": risk_mgr.compute_diagnostics(),
        "risk_engine": risk_mgr,   # returned for dashboard printing
        "risk_event_warnings": risk_event_warnings,
        "risk_blocked_attempts": risk_blocked_attempts,
        "risk_events": risk_events,
        "risk_snapshots": risk_snapshots,
        "risk_bearing_snapshots": risk_bearing_snapshots,
        "signal_density_report": signal_density_report,
    }

# ------------------------------------------------------------------ #
#  MAIN RUNNER                                                        #
# ------------------------------------------------------------------ #
def run_backtest(df: pd.DataFrame) -> None:
    import shutil
    from core.data_collector import DataCollector
    from core.ai_engine import TradingAI

    profiler = get_runtime_profiler(Config)

    # Prompt 28.3: force runtime market-structure enrichment here as well,
    # because custom runners can load candles directly and bypass fetch_data().
    if profiler:
        with profiler.phase("market_structure_enrichment_seconds"):
            df = _ensure_market_structure_features(df, strict=bool(getattr(Config, "BACKTEST_MARKET_STRUCTURE_STRICT_AUDIT", False)))
    else:
        df = _ensure_market_structure_features(df, strict=bool(getattr(Config, "BACKTEST_MARKET_STRUCTURE_STRICT_AUDIT", False)))
    _ms_present, _ms_missing, _ms_rate, _ms_missing_cols = _market_structure_feature_status(df)
    print(
        "  [MarketStructureRuntime] Final runtime audit before simulation: "
        f"available={_ms_present} | missing={_ms_missing} | rate={_ms_rate:.2f}%"
    )
    if _ms_missing:
        print(f"  [MarketStructureRuntime] Final missing columns: {_ms_missing_cols[:8]}")

    # Pulisce la cartella dei grafici solo quando i chart HTML sono abilitati.
    charts_enabled = bool(getattr(Config, "BACKTEST_SAVE_CHARTS", True))
    if charts_enabled:
        if os.path.exists(CHARTS_DIR):
            try:
                shutil.rmtree(CHARTS_DIR)
            except Exception:
                pass
        os.makedirs(CHARTS_DIR, exist_ok=True)

    print("\n==================================================")
    print("  AVVIO BACKTEST MULTI-RISCHIO CON CONGIUNZIONE GENETICA")
    print("==================================================")
    print(f"  Candele caricate : {len(df)}")
    print(f"  Asset            : {Config.SYMBOL} ({Config.TIMEFRAME})")
    print(f"  Soglia Trending  : {Config.TRENDING_THRESHOLD} (ADX > {Config.ADX_THRESHOLD})")
    print(f"  Soglia Ranging   : {Config.RANGING_THRESHOLD} (ADX <= {Config.ADX_THRESHOLD})")
    print(f"  Stop Loss ATR    : {Config.ATR_MULT:.2f}x")
    print(f"  Target R:R       : {Config.TRENDING_RR:.2f}x (Trending) / {Config.RANGING_RR:.2f}x (Ranging)")
    print("==================================================")
    
    # Gestione Inizializzazione AI & Addestramento
    ai = TradingAI()
    original_strategy_mode = Config.STRATEGY_MODE
    ai_metrics = {}
    features_df = None
    wf_folds = None
    training_audit = {
        "training_source": "NONE",
        "samples": 0,
        "using_expanded_training": False,
        "assets": {},
        "warnings": [],
    }

    if Config.AI_ENABLED:
        print("🤖 [AI INIT] Estrazione features storiche causali per il dataset...")
        from core.data_collector import DataCollector
        from core.walk_forward import WalkForwardPipeline
        if profiler:
            with profiler.phase("feature_collection_seconds"):
                features_df = DataCollector.collect_from_backtest_mem(df)
        else:
            features_df = DataCollector.collect_from_backtest_mem(df)
        
        # Generiamo i fold walk-forward puri ed esportiamo un audit machine-readable.
        # Se il dataset è troppo corto (es. 1000 candles con N=2000), il report segnala
        # esplicitamente che non esiste vera validazione OOS walk-forward.
        def _audit_wf():
            return WalkForwardPipeline.audit_and_export(
                total_len=len(df),
                N=getattr(Config, "WF_TRAIN_SIZE", 2000),
                M=getattr(Config, "WF_TEST_SIZE", 500),
                embargo_gap=Config.EMBARGO_GAP,
                train_mode=getattr(Config, "WF_TRAIN_MODE", "rolling"),
                df=df,
                label_horizon=getattr(Config, "WF_LABEL_HORIZON", 100),
                path="data/walkforward_audit_report.json",
                min_train_size=getattr(Config, "WF_MIN_TRAIN_SIZE", 250),
                adaptive=getattr(Config, "WF_AUTO_ADAPTIVE", True),
                min_test_size=getattr(Config, "WF_MIN_TEST_SIZE", 100),
            )
        if profiler:
            with profiler.phase("walkforward_audit_seconds"):
                wf_folds = _audit_wf()
        else:
            wf_folds = _audit_wf()
        if bool(getattr(Config, "BACKTEST_PRINT_WF_TIMELINE", True)):
            WalkForwardPipeline.print_timeline(wf_folds, len(df))
        else:
            print(f"  [WalkForwardAudit] Timeline suppressed by fast/quiet mode ({len(wf_folds or [])} folds).")
        
        # Prefer the Prompt 19 expanded multi-asset meta-label dataset when present.
        # The legacy BTC-only generator is kept as a fallback for offline smoke tests.
        global_train_df = None
        using_expanded_training = False

        if getattr(Config, "AI_USE_EXPANDED_DATASET", True):
            try:
                from core.training_dataset_loader import MultiAssetTrainingDatasetLoader
                if MultiAssetTrainingDatasetLoader.expanded_dataset_exists():
                    global_train_df, training_report = MultiAssetTrainingDatasetLoader.load_expanded_training_dataset()
                    using_expanded_training = True
                    print(
                        "🧠 [AI DATASET] Using expanded multi-asset training dataset: "
                        f"{training_report.rows_after_cleaning} samples | "
                        f"assets={training_report.per_asset_counts}"
                    )
                    training_audit = {
                        "training_source": "expanded_multi_asset",
                        "samples": int(training_report.rows_after_cleaning),
                        "using_expanded_training": True,
                        "assets": dict(training_report.per_asset_counts),
                        "warnings": list(training_report.warnings or []),
                    }
                    if training_report.warnings:
                        print(f"⚠️ [AI DATASET] Warnings: {training_report.warnings[:5]}")
            except Exception as e:
                print(f"⚠️ [AI DATASET] Expanded loader unavailable; falling back to legacy BTC-only training. Reason: {e}")

        if global_train_df is None:
            # Generiamo un dataset di addestramento globale sicuro (con purging e localizzazione)
            def _generate_local_training_dataset():
                return DataCollector.generate_training_dataset(
                    df=df,
                    train_start=0,
                    train_end=len(df) - 1,
                    features_df=features_df,
                    label_horizon=100
                )
            if profiler:
                with profiler.phase("training_dataset_generation_seconds"):
                    global_train_df = _generate_local_training_dataset()
            else:
                global_train_df = _generate_local_training_dataset()
            training_audit = {
                "training_source": f"local_{str(getattr(Config, 'SYMBOL', 'UNKNOWN')).replace('/', '').replace(':', '').lower()}_derived",
                "samples": int(len(global_train_df)),
                "using_expanded_training": False,
                "assets": {str(getattr(Config, "SYMBOL", "UNKNOWN")): int(len(global_train_df))},
                "warnings": ["expanded_multi_asset_dataset_not_used"],
            }

        samples_count = len(global_train_df)
        training_audit["samples"] = int(samples_count)
        print(
            "🧾 [TrainingSource] "
            f"source={training_audit.get('training_source')} | "
            f"samples={training_audit.get('samples')} | "
            f"expanded={training_audit.get('using_expanded_training')}"
        )
        
        if samples_count >= Config.AI_MIN_SAMPLES:
            # Salviamo il dataset legacy solo quando non stiamo usando il parquet multi-asset adattato.
            if not using_expanded_training:
                try:
                    import polars as pl
                    from core.data_collector import DatasetIntegrity, DatasetVersioning
                    
                    global_train_df_pl = pl.DataFrame(global_train_df)
                    global_train_df_pl = DatasetIntegrity.validate_schema(global_train_df_pl, is_features=True)
                    global_train_df_pl = DatasetIntegrity.handle_missing_data(global_train_df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
                    global_train_df_pl = DatasetIntegrity.detect_and_remove_duplicates(global_train_df_pl)
                    
                    DatasetVersioning.write_parquet_with_metadata(global_train_df_pl, Config.AI_FEATURES_PATH, is_features=True)
                    print(f"💾 Salvati {samples_count} campioni completi in formato Parquet: {Config.AI_FEATURES_PATH}")
                except Exception as e:
                    print(f"[WARN] Impossibile salvare features Parquet: {e}")
            else:
                print(f"💾 Dataset training compatibile scritto in: {Config.AI_FEATURES_PATH}")
                
            print("🧠 [AI INIT] Addestramento modello globale XGBoost sicuro...")
            if profiler:
                with profiler.phase("ai_training_seconds"):
                    ai_metrics = ai.train(features_df=global_train_df)
            else:
                ai_metrics = ai.train(features_df=global_train_df)
            if ai.is_ready():
                Config.STRATEGY_MODE = "AI_HYBRID"
                print(f"🎯 [AI CONFIG] STRATEGY_MODE impostata a '{Config.STRATEGY_MODE}' per il backtest.")
            else:
                print("⚠️ [AI INIT] Addestramento completato ma modello non pronto. Fallback su strategia base.")
        else:
            print(f"⚠️ [AI INIT] Campioni storici insufficienti ({samples_count}/{Config.AI_MIN_SAMPLES}) per attivare l'AI.")

    profiles = [
        {"name": "Basso Rischio (LOW)", "risk": 0.03, "leverage": 4.0},
        {"name": "Medio Rischio (MEDIUM)", "risk": 0.07, "leverage": 8.0},
        {"name": "Alto Rischio (HIGH)", "risk": 0.15, "leverage": 10.0},
        {"name": "Rischio Dinamico (DYNAMIC)", "risk": "DYNAMIC", "leverage": 0.0},
    ]

    risk_filter = str(getattr(Config, "BACKTEST_RISK_PROFILE", "ALL") or "ALL").upper()
    if risk_filter != "ALL":
        profiles = [p for p in profiles if risk_filter in str(p["name"]).upper()]
        if not profiles:
            print(f"⚠️ [Backtest] Unknown BACKTEST_RISK_PROFILE={risk_filter}; fallback to DYNAMIC.")
            profiles = [{"name": "Rischio Dinamico (DYNAMIC)", "risk": "DYNAMIC", "leverage": 0.0}]

    results = {}
    for p in profiles:
        if p["risk"] == "DYNAMIC":
            print(f"  Simulazione {p['name']} (Gestione Dinamica)...")
        else:
            print(f"  Simulazione {p['name']} (Rischio: {p['risk']*100:.1f}%, Leva Max: {p['leverage']:.1f}x)...")
        # Salviamo i grafici del trade solo se corrisponde alla classe selezionata nel Config
        is_selected = (Config.RISK_CLASS == p["name"].split()[-1].replace("(", "").replace(")", ""))
        save_charts_for_profile = bool(charts_enabled and is_selected)
        phase_name = "simulation_" + ("dynamic" if p["risk"] == "DYNAMIC" else str(p["name"].split()[-1].replace("(", "").replace(")", "").lower())) + "_seconds"
        if profiler:
            with profiler.phase(phase_name):
                res = simulate_backtest(df, p["risk"], p["leverage"], save_charts=save_charts_for_profile, features_df=features_df, wf_folds=wf_folds)
        else:
            res = simulate_backtest(df, p["risk"], p["leverage"], save_charts=save_charts_for_profile, features_df=features_df, wf_folds=wf_folds)
        results[p["name"]] = res

    # Stampa tabella comparativa finale
    sep = "=" * 87
    print(f"\n{sep}")
    print(f"  REPORT COMPARATIVO CLASSI DI RISCHIO COMPILATE")
    print(sep)
    print(f"{'Profilo Rischio':<28}{'Rischio %':<11}{'Leva Max':<10}{'Saldo Finale':<18}{'Net PnL %':<12}{'Max DD %':<10}")
    print("-" * 87)
    for p in profiles:
        res = results[p["name"]]
        net_pct = ((res["final_balance"] - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        net_pct_str = f"{net_pct:+.2f}%"
        dd_str = f"{res['max_drawdown']:.1f}%"
        if p["risk"] == "DYNAMIC":
            r_str = "Dinamico"
            l_str = "Dinamica"
        else:
            r_str = f"{p['risk']*100:.1f}%"
            l_str = f"{p['leverage']:.1f}x"
        print(f"{p['name']:<28}{r_str:<11}{l_str:<10}{res['final_balance']:<18.2f}{net_pct_str:<12}{dd_str:<10}")
    print(sep)

    # Dettaglio del profilo selezionato
    selected_name = f"Alto Rischio (HIGH)" if Config.RISK_CLASS == "HIGH" else (f"Medio Rischio (MEDIUM)" if Config.RISK_CLASS == "MEDIUM" else (f"Rischio Dinamico (DYNAMIC)" if Config.RISK_CLASS == "DYNAMIC" else "Basso Rischio (LOW)"))
    if selected_name not in results and results:
        selected_name = next(iter(results.keys()))
    sel_res = results.get(selected_name)
    if sel_res:
        print(f"\n  Dettaglio Profilo Selezionato ({selected_name}):")
        print(f"    Trade totali   : {sel_res['total_trades']}")
        print(f"    Vinti (Full TP): {sel_res['wins']}")
        print(f"    Vinti (Parz TP): {sel_res.get('partial_wins', 0)}")
        print(f"    Pareggiati (BE): {sel_res.get('breakevens', 0)}")
        print(f"    Persi          : {sel_res['losses']}")
        print(f"    Win Rate (Tot) : {sel_res['win_rate']:.1f}%")
        if sel_res.get("risk_blocked_attempts", 0):
            print(f"    Trade bloccati dal Risk Engine: {sel_res['risk_blocked_attempts']}")
        if len(sel_res['trades']) > 0:
            print("\n    Ultimi 5 trade:")
            for t in sel_res['trades'][-5:]:
                icon = f"[{t['result']}]"
                ai_pct_str = f" | AI Conf: {t['ai_prob']:.1f}%" if "ai_prob" in t else ""
                pnl_value = float(t.get("realized_pnl", t.get("pnl", 0.0)) or 0.0)
                print(f"      {icon:<12} {t['side']:<4} | PnL: {pnl_value:+.4f} | Saldo: {t['balance']:.2f} EUR{ai_pct_str}")

        # Dynamic Risk Engine dashboard for selected profile
        sel_engine = sel_res.get("risk_engine")
        if sel_engine is not None:
            sel_engine.print_risk_dashboard()
            # Export risk log for offline analysis
            os.makedirs("data", exist_ok=True)
            sel_engine.export_risk_log("data/risk_log.csv", fmt="csv")
            sel_engine.export_risk_log("data/risk_log.json", fmt="json")
            if hasattr(sel_engine, "export_trade_events"):
                sel_engine.export_trade_events("data/risk_event_log.json")
            lifecycle_report = _write_lifecycle_report(
                sel_res,
                "data/lifecycle_consistency_report.json",
                charting_enabled=bool(charts_enabled),
            )
            print(f"  [LifecycleAudit] Report exported -> data/lifecycle_consistency_report.json  ({lifecycle_report['status']})")
            if lifecycle_report["status"] != "PASS":
                print(
                    "  [LIFECYCLE AUDIT WARNING] "
                    f"closed={lifecycle_report['closed_trades']} | "
                    f"risk_events={lifecycle_report['risk_events']} | "
                    f"risk_sizing={lifecycle_report['risk_bearing_snapshots']} | "
                    f"visualized={lifecycle_report['visualized_trades']} | "
                    f"charting_enabled={lifecycle_report.get('charting_enabled', True)} | "
                    f"ignored_no_charts={lifecycle_report.get('visualization_mismatch_ignored_due_to_no_charts', False)} | "
                    f"balance_mismatches={lifecycle_report['balance_mutation_mismatches']}"
                )
            for warning_msg in sel_res.get("risk_event_warnings", []):
                print(f"  [RISK AUDIT WARNING] {warning_msg}")

            signal_report = sel_res.get("signal_density_report")
            if signal_report:
                funnel = signal_report.get("funnel", {})
                print("\n========================================================================================")
                print("  SIGNAL DENSITY + THRESHOLD CALIBRATION DIAGNOSTICS")
                print("========================================================================================")
                print(f"  Bars evaluated           : {funnel.get('bars_evaluated', 0)}")
                print(f"  Technical candidates     : {funnel.get('technical_candidates', 0)}  ({funnel.get('technical_candidate_rate_pct', 0.0):.2f}%)")
                print(f"  Meta accepted            : {funnel.get('meta_accepted', 0)}  ({funnel.get('meta_acceptance_rate_pct', 0.0):.2f}% of technical)")
                print(f"  Pending triggers created : {funnel.get('pending_triggers_created', 0)}")
                print(f"  Pending triggers filled  : {funnel.get('pending_triggers_filled', 0)}  ({funnel.get('pending_fill_rate_pct', 0.0):.2f}%)")
                print(f"  Opened trades            : {funnel.get('opened_trades', 0)}")
                print(f"  Closed trades            : {funnel.get('closed_trades', 0)}")
                print(f"  Cost-aware pass          : {funnel.get('cost_aware_pass', 0)}")
                print(f"  Cost-aware fail          : {funnel.get('cost_aware_fail', 0)}")
                net_dist = signal_report.get('expected_net_edge_distribution', {})
                cost_dist = signal_report.get('expected_cost_bps_distribution', {})
                if net_dist.get('count', 0):
                    print(f"  Avg expected net edge    : {net_dist.get('mean', 0.0):+.4f} R")
                    print(f"  Avg expected cost        : {cost_dist.get('mean', 0.0):.2f} bps")
                structure_dist = signal_report.get('structure_score_distribution', {})
                archetypes = signal_report.get('setup_archetype_counts', {})
                if structure_dist.get('count', 0):
                    print(f"  Avg structure score      : {structure_dist.get('mean', 0.0):.2f}")
                if archetypes:
                    print("  Setup archetypes          : " + ", ".join([f"{k}={v}" for k, v in list(archetypes.items())[:5]]))
                archetype_diag = signal_report.get("setup_archetype_diagnostics", {})
                ms_audit = archetype_diag.get("runtime_market_structure_feature_audit", {}) if archetype_diag else {}
                if ms_audit:
                    print(
                        "  Runtime MS features       : "
                        f"available={ms_audit.get('available_count', 0)} | "
                        f"missing={ms_audit.get('missing_count', 0)} | "
                        f"rate={ms_audit.get('available_rate_pct', 0.0):.2f}%"
                    )
                diag_interp = archetype_diag.get("interpretation", []) if archetype_diag else []
                if diag_interp:
                    print("  Setup diagnostics         : " + " | ".join(diag_interp[:2]))
                score_diag = (archetype_diag.get("candidate_score_diagnostics", {}) if archetype_diag else {})
                inactive = [name for name, row_diag in score_diag.items() if row_diag.get("count_score_gte_40", 0) == 0]
                if inactive:
                    print("  Inactive archetypes       : " + ", ".join(inactive[:5]))
                gate_fails = archetype_diag.get("archetype_gate_fail_counts", {}) if archetype_diag else {}
                if gate_fails:
                    print("  Archetype gate fails      : " + ", ".join([f"{k}={v}" for k, v in list(gate_fails.items())[:5]]))
                ai_audit = signal_report.get("ai_prediction_audit", {})
                if ai_audit:
                    src_counts = ai_audit.get("prediction_source_counts", {})
                    print(
                        "  AI prediction audit       : "
                        f"neutral={ai_audit.get('neutral_probability_count', 0)} "
                        f"({ai_audit.get('neutral_probability_rate_pct', 0.0):.2f}%) | "
                        f"not_ready={ai_audit.get('model_not_ready_count', 0)} | "
                        f"sources=" + ", ".join([f"{k}={v}" for k, v in list(src_counts.items())[:4]])
                    )
                    missing_ai = ai_audit.get("top_missing_features", {})
                    if missing_ai:
                        print("  AI missing features       : " + ", ".join([f"{k}={v}" for k, v in list(missing_ai.items())[:6]]))
                disabled_arches = _disabled_archetypes_from_config() | _negative_realized_archetypes_from_report()
                if disabled_arches:
                    print("  Disabled archetypes       : " + ", ".join(sorted(disabled_arches)))
                if bool(getattr(Config, "ASSET_ARCHETYPE_GATING_ENABLED", True)):
                    paper_universe = str(getattr(Config, "PAPER_ASSET_UNIVERSE", ""))
                    excluded_assets = str(getattr(Config, "PAPER_EXCLUDED_ASSETS", ""))
                    cost_rules = str(getattr(Config, "COST_ROBUSTNESS_DISABLED_ASSET_ARCHETYPES", ""))
                    print(
                        "  Asset/cost gates          : "
                        f"paper_universe={paper_universe or 'none'} | "
                        f"excluded={excluded_assets or 'none'} | "
                        f"rules={cost_rules or 'none'}"
                    )
                top_opt = signal_report.get('cost_aware_threshold_optimization', [])[:3]
                if top_opt:
                    print("\n  Cost-aware threshold candidates (diagnostic):")
                    for row_opt in top_opt:
                        print(
                            "    - "
                            f"p>={row_opt.get('prob_threshold')} q>={row_opt.get('quality_threshold')} | "
                            f"pass={row_opt.get('would_pass')} | "
                            f"avg_net={row_opt.get('avg_expected_net_edge_r'):+.4f}R | "
                            f"avg_cost={row_opt.get('avg_expected_cost_bps'):.2f}bps"
                        )
                adaptive = signal_report.get('adaptive_regime_threshold_optimization', {})
                regimes = adaptive.get('regimes', {}) if adaptive else {}
                if regimes:
                    print("\n  Adaptive regime threshold candidates (diagnostic-only):")
                    for regime_name, regime_report in list(regimes.items())[:6]:
                        best = regime_report.get('best_threshold') or {}
                        if not best:
                            continue
                        print(
                            "    - "
                            f"{regime_name}: p>={best.get('probability_threshold')} "
                            f"q>={best.get('quality_threshold')} | "
                            f"pass={best.get('selected_count')} | "
                            f"avg_net={best.get('avg_expected_net_edge_r'):+.4f}R | "
                            f"status={best.get('status')}"
                        )
                    print("  [AdaptiveRegimeThresholds] Full report -> data/adaptive_regime_threshold_report.json")

                top_reasons = list(signal_report.get('rejection_reasons', {}).items())[:5]
                if top_reasons:
                    print("\n  Top rejection reasons:")
                    for reason, count in top_reasons:
                        print(f"    - {reason}: {count}")
                print("  [SignalDensity] Full report -> data/signal_density_report.json")
            
            # Genera il report di performance sui regimi di mercato
            if "trades" in sel_res and sel_res["trades"]:
                from core.regime_analyzer import RegimePerformanceAnalyzer
                RegimePerformanceAnalyzer.generate_report(sel_res["trades"], df, "data/regime_report.json")
                archetype_perf = _build_archetype_performance_report(sel_res["trades"], "data/archetype_performance_report.json")
                perf_rows = archetype_perf.get("by_archetype", {})
                if perf_rows:
                    print("\n========================================================================================")
                    print("  REALIZED ARCHETYPE PERFORMANCE")
                    print("========================================================================================")
                    for arch_name, row_perf in sorted(perf_rows.items(), key=lambda kv: kv[1].get("trades", 0), reverse=True):
                        print(
                            "  - "
                            f"{arch_name}: trades={row_perf.get('trades', 0)} | "
                            f"WR={row_perf.get('win_rate_pct', 0.0):.1f}% | "
                            f"avgPnL={row_perf.get('avg_pnl', 0.0):+.4f} | "
                            f"avgR={row_perf.get('avg_r', 0.0):+.3f}"
                        )
                    print("  [ArchetypePerformance] Full report -> data/archetype_performance_report.json")
                    stability_warnings = archetype_perf.get("stability_warnings", [])
                    if stability_warnings:
                        print("\n  Edge stability guardrails:")
                        for msg in stability_warnings[:6]:
                            print(f"    - {msg}")

                monthly_report = _export_equity_curve_and_monthly_report(
                    sel_res["trades"],
                    INITIAL_BALANCE,
                    "data/equity_curve.csv",
                    "data/monthly_performance_report.json",
                )
                readiness_report = _build_paper_readiness_report(
                    result=sel_res,
                    lifecycle_report=lifecycle_report,
                    archetype_report=archetype_perf,
                    signal_report=signal_report,
                    training_audit=training_audit,
                    wf_folds=wf_folds,
                    output_path="data/paper_readiness_report.json",
                )
                print("\n========================================================================================")
                print("  EDGE STABILITY + PAPER READINESS")
                print("========================================================================================")
                tf_profile = getattr(Config, "ACTIVE_TIMEFRAME_PROFILE", {}) or {"timeframe": getattr(Config, "TIMEFRAME", "unknown")}
                print(f"  Timeframe                : {tf_profile.get('timeframe')} ({tf_profile.get('minutes', '?')}m, {tf_profile.get('approx_days', 0):.1f} days)")
                print(f"  Training source          : {training_audit.get('training_source')} ({training_audit.get('samples')} samples)")
                print(f"  Equity curve export      : data/equity_curve.csv")
                print(f"  Monthly report export    : data/monthly_performance_report.json")
                print(f"  Paper readiness          : {readiness_report.get('status')}")
                if readiness_report.get("blockers"):
                    print("  Blockers:")
                    for msg in readiness_report.get("blockers", [])[:6]:
                        print(f"    - {msg}")
                if readiness_report.get("warnings"):
                    print("  Warnings:")
                    for msg in readiness_report.get("warnings", [])[:8]:
                        print(f"    - {msg}")
                print("  [PaperReadiness] Full report -> data/paper_readiness_report.json")

    if profiler:
        try:
            profiler.add_counter("candles", int(len(df)))
            profiler.add_counter("risk_profiles_run", list(results.keys()))
            if sel_res:
                profiler.add_counter("selected_profile", selected_name)
                profiler.add_counter("selected_trades", int(sel_res.get("total_trades", 0) or 0))
                profiler.add_counter("selected_final_balance", float(sel_res.get("final_balance", 0.0) or 0.0))
                profiler.add_counter("selected_max_drawdown_pct", float(sel_res.get("max_drawdown", 0.0) or 0.0))
        except Exception:
            pass

    # Stampa metriche dell'AI se abilitata e addestrata
    if Config.AI_ENABLED and bool(getattr(Config, "BACKTEST_PRINT_WF_FOLD_TABLE", True)):
        print("\n" + "=" * 120)
        print("🧠 DETTAGLI E DIAGNOSTICA DEL PIPELINE DI VALIDAZIONE WALK-FORWARD (PURGED + EMBARGO)")
        print("=" * 120)
        
        # Se abbiamo modelli Walk-Forward nella cache
        if hasattr(ai, "_wf_models") and ai._wf_models:
            print(f"{'Fold':<5}| {'Train Range':<15} | {'Embargo Range':<15} | {'Test Range':<15} | {'Purged':<8} | {'Eff. Train':<11} | {'Eff. Test':<10} | {'Mode':<17} | {'Model Acc':<9} | {'F1':<8}")
            print("-" * 135)
            
            fold_idx = 1
            train_accs = []
            test_accs = []
            f1s = []
            total_purged = 0
            
            for k in sorted(ai._wf_models.keys()):
                m = ai._wf_models[k]
                if not m["is_trained"]:
                    continue
                    
                train_range = f"{m['train_start']}->{m['train_end']}"
                emb_range = f"{m['embargo_start']}->{m['embargo_end']}"
                test_range = f"{m['test_start']}->{m['test_end']}"
                
                purged = m["num_purged_samples"]
                eff_train = m["effective_train_size"]
                eff_test = m["effective_test_size"]
                
                mode = "EVAL_ONLY_GLOBAL" if m.get("evaluation_only") else "LOCAL_RETRAIN"
                val_acc = f"{m['accuracy']*100:.2f}%"
                f1_val = f"{m['f1']*100:.2f}%"
                
                print(f" {fold_idx:02d}  | {train_range:<15} | {emb_range:<15} | {test_range:<15} | {purged:<8} | {eff_train:<11} | {eff_test:<10} | {mode:<17} | {val_acc:<9} | {f1_val:<8}")
                
                if not m.get("evaluation_only"):
                    train_accs.append(m["train_accuracy"])
                    test_accs.append(m["accuracy"])
                    f1s.append(m["f1"])
                total_purged += purged
                fold_idx += 1
                
            print("-" * 135)
            eval_only_count = sum(1 for m in ai._wf_models.values() if m.get("evaluation_only"))
            if eval_only_count:
                print(
                    f"  [WF EVALUATION-ONLY] {eval_only_count} fold valutati con modello globale. "
                    "Nessun retraining locale su campioni microscopici."
                )
            if train_accs:
                avg_train_acc = sum(train_accs) / len(train_accs)
                avg_test_acc = sum(test_accs) / len(test_accs)
                avg_f1 = sum(f1s) / len(f1s)
                diff = avg_train_acc - avg_test_acc
                
                avg_eff_train = int(sum(m['effective_train_size'] for m in ai._wf_models.values() if m['is_trained'])/len(train_accs))
                avg_eff_test = int(sum(m['effective_test_size'] for m in ai._wf_models.values() if m['is_trained'])/len(train_accs))
                
                print(f" MED | {'-':<15} | {'-':<15} | {'-':<15} | {int(total_purged/len(train_accs)):<8} | {avg_eff_train:<11} | {avg_eff_test:<10} | {avg_train_acc*100:.2f}% | {avg_test_acc*100:.2f}% | {avg_f1*100:.2f}%")
                print("=" * 120)
                print(f"  [WALK-FORWARD MEDIA ({len(train_accs)} finestre)]")
                print(f"  Accuratezza media in Training (In-Sample) : {avg_train_acc*100:.2f}%")
                print(f"  Accuratezza media Out-of-Sample (Holdout)  : {avg_test_acc*100:.2f}%")
                print(f"  Differenza media (Training vs Holdout)     : {diff*100:.2f}%")
                print(f"  F1-Score medio Out-of-Sample (Holdout)     : {avg_f1*100:.2f}%")
                
                if diff > 0.10:  # Differenza > 10%
                    print("⚠️ WARNING: Possibile Overfitting! Lo scarto supera il 10%.")
                
                # Dettaglio ultimo modello
                last_limit = max(ai._wf_models.keys())
                last_model = ai._wf_models[last_limit]
                if last_model["is_trained"]:
                    print(f"\n  [ULTIMO MODELLO WALK-FORWARD (Limite: {last_limit})]")
                    print(f"  Accuratezza Training : {last_model['train_accuracy']*100:.2f}%")
                    print(f"  Accuratezza Holdout  : {last_model['accuracy']*100:.2f}%")
                    
                    print("\n📊 IMPORTANZA DELLE FEATURES (Top 10):")
                    importances = last_model.get("importances", {})
                    for idx, (feat, val) in enumerate(list(importances.items())[:10]):
                        print(f"  {idx+1:02d}. {feat:<20}: {val*100:.2f}%")
            else:
                print("  Nessun fold locale è stato riaddestrato: WF in modalità evaluation-only/global model.")
                print("=" * 120)
        else:
            diff = ai.train_accuracy - ai.accuracy
            print(f"  Accuratezza in Training (In-Sample) : {ai.train_accuracy*100:.2f}%")
            print(f"  Accuratezza Out-of-Sample (Holdout)  : {ai.accuracy*100:.2f}%")
            print(f"  Differenza (Training vs Out-of-Sample): {diff*100:.2f}%")
            if diff > 0.10:
                print("⚠️ WARNING: Possibile Overfitting! Lo scarto supera il 10%.")
            print(f"  F1-Score Modello   : {ai.f1*100:.2f}%")
            print(f"  Campioni Dataset   : {ai_metrics.get('samples', 0)}")
            
            print("\n📊 IMPORTANZA DELLE FEATURES (Top 10):")
            importances = ai_metrics.get("importances", {})
            for idx, (feat, val) in enumerate(list(importances.items())[:10]):
                print(f"  {idx+1:02d}. {feat:<20}: {val*100:.2f}%")
        print("=" * 120 + "\n")

    # Ripristina la strategy mode originale
    Config.STRATEGY_MODE = original_strategy_mode
    print()

if __name__ == "__main__":
    print("[INIT] Avvio backtest...")
    df = asyncio.run(fetch_data())
    run_backtest(df)
