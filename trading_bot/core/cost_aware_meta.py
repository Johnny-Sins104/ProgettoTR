"""
core/cost_aware_meta.py — Cost-aware meta-label threshold diagnostics
=====================================================================

This module converts gross meta-model expectancy into execution-cost-adjusted
expectancy.  It is deliberately lightweight and deterministic so it can be used
inside backtests without coupling the signal layer to the full stochastic
execution simulator.

Units
-----
- gross_ev_r: expectancy in R units, before costs
- expected_round_trip_cost_bps: expected entry+exit friction in basis points
- expected_cost_r: expected execution cost converted to R units
- expected_net_edge_r: gross_ev_r - expected_cost_r - minimum_required_edge_r
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List
import json
from pathlib import Path

from config import Config


@dataclass(frozen=True)
class CostAwareEstimate:
    gross_ev_r: float
    expected_round_trip_cost_bps: float
    expected_cost_r: float
    expected_net_edge_r: float
    cost_to_edge_ratio: float
    fill_probability: float
    vol_regime: str
    stop_distance_bps: float
    accepted_cost_aware: bool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: round(v, 8) if isinstance(v, float) else v for k, v in d.items()}


class CostAwareMetaLabeler:
    """Static utilities for cost-aware threshold analysis."""

    # Conservative baseline round-trip costs in bps for crypto futures.
    # These are deliberately lower than stress-test execution diagnostics so
    # they act as a decision prior rather than a worst-case veto.
    BASE_ROUND_TRIP_COST_BPS = {
        "LOW_VOL": 6.0,
        "NORMAL": 10.0,
        "HIGH_VOL": 25.0,
        "EXTREME": 75.0,
    }
    FILL_PROB_BY_VOL_REGIME = {
        "LOW_VOL": 0.98,
        "NORMAL": 0.95,
        "HIGH_VOL": 0.88,
        "EXTREME": 0.72,
    }

    @staticmethod
    def normalize_probability(p: float) -> float:
        p = float(p or 0.0)
        return max(0.0, min(1.0, p / 100.0 if p > 1.0 else p))

    @classmethod
    def gross_ev_r(cls, probability: float, rr_ratio: float) -> float:
        p = cls.normalize_probability(probability)
        rr = max(0.0, float(rr_ratio or 0.0))
        return (p * rr) - (1.0 - p)

    @classmethod
    def classify_vol_regime(cls, atr_ratio: float = 1.0, fallback: str = "NORMAL") -> str:
        try:
            r = float(atr_ratio)
        except Exception:
            return fallback or "NORMAL"
        if r < 0.75:
            return "LOW_VOL"
        if r <= 1.40:
            return "NORMAL"
        if r <= 2.00:
            return "HIGH_VOL"
        return "EXTREME"

    @classmethod
    def estimate_round_trip_cost_bps(
        cls,
        *,
        vol_regime: str = "NORMAL",
        atr_pct: float = 0.0,
        order_type: str = "LIMIT",
        entry_type: str = "BREAKOUT",
    ) -> float:
        regime = (vol_regime or "NORMAL").upper()
        base = cls.BASE_ROUND_TRIP_COST_BPS.get(regime, cls.BASE_ROUND_TRIP_COST_BPS["NORMAL"])

        # ATR term: high ATR% expands adverse selection.  Keep it bounded so
        # diagnostics remain stable across synthetic and real datasets.
        atr_pct = max(0.0, float(atr_pct or 0.0))
        atr_bps_component = min(40.0, atr_pct * 2.0)  # 1% ATR -> +2 bps, capped.

        order_type = (order_type or "LIMIT").upper()
        entry_type = (entry_type or "BREAKOUT").upper()
        urgency = 0.0
        if order_type == "MARKET":
            urgency += 3.0
        elif order_type == "STOP":
            urgency += 5.0
        if entry_type == "BREAKOUT":
            urgency += 2.0

        return float(max(0.0, base + atr_bps_component + urgency))

    @classmethod
    def estimate(
        cls,
        *,
        probability: float,
        rr_ratio: float,
        entry_price: float,
        stop_loss: float | None = None,
        atr_val: float = 0.0,
        atr_ratio: float = 1.0,
        atr_pct: float = 0.0,
        vol_regime: str | None = None,
        order_type: str = "LIMIT",
        entry_type: str = "BREAKOUT",
        min_required_edge_r: float | None = None,
    ) -> CostAwareEstimate:
        gross = cls.gross_ev_r(probability, rr_ratio)
        entry = max(1e-12, float(entry_price or 0.0))
        if stop_loss is not None and float(stop_loss or 0.0) > 0:
            stop_distance_bps = abs(entry - float(stop_loss)) / entry * 10000.0
        elif atr_val and float(atr_val) > 0:
            stop_distance_bps = abs(float(atr_val) * float(getattr(Config, "ATR_MULT", 2.0))) / entry * 10000.0
        else:
            stop_distance_bps = 100.0  # safe 1% fallback
        stop_distance_bps = max(1.0, stop_distance_bps)

        regime = (vol_regime or cls.classify_vol_regime(atr_ratio)).upper()
        if str(getattr(Config, "EXECUTION_COST_MODEL", "base")).lower() in {"base", "conservative", "severe"}:
            try:
                from core.execution_cost_model import ExecutionCostModel

                exec_est = ExecutionCostModel.estimate_round_trip_bps(
                    price=entry,
                    atr_val=atr_val,
                    atr_pct=atr_pct,
                    atr_ratio=atr_ratio,
                    vol_regime=regime,
                    order_type=order_type,
                    entry_type=entry_type,
                    symbol=getattr(Config, "SYMBOL", "BTC/USDT"),
                    timeframe=getattr(Config, "TIMEFRAME", "15m"),
                    cost_model=getattr(Config, "EXECUTION_COST_MODEL", "base"),
                )
                cost_bps = float(exec_est.total_round_trip_cost_bps)
            except Exception:
                cost_bps = cls.estimate_round_trip_cost_bps(
                    vol_regime=regime,
                    atr_pct=atr_pct,
                    order_type=order_type,
                    entry_type=entry_type,
                )
        else:
            cost_bps = cls.estimate_round_trip_cost_bps(
                vol_regime=regime,
                atr_pct=atr_pct,
                order_type=order_type,
                entry_type=entry_type,
            )
        cost_r = cost_bps / stop_distance_bps
        min_edge = float(min_required_edge_r if min_required_edge_r is not None else getattr(Config, "META_MIN_NET_EDGE_R", 0.0))
        net = gross - cost_r - min_edge
        ratio = cost_r / abs(gross) if abs(gross) > 1e-12 else float("inf")
        max_ratio = float(getattr(Config, "META_MAX_COST_TO_EDGE_RATIO", 1.0))
        fill_prob = cls.FILL_PROB_BY_VOL_REGIME.get(regime, 0.95)
        accepted = bool(gross > 0.0 and net > 0.0 and ratio <= max_ratio)
        return CostAwareEstimate(
            gross_ev_r=gross,
            expected_round_trip_cost_bps=cost_bps,
            expected_cost_r=cost_r,
            expected_net_edge_r=net,
            cost_to_edge_ratio=ratio,
            fill_probability=fill_prob,
            vol_regime=regime,
            stop_distance_bps=stop_distance_bps,
            accepted_cost_aware=accepted,
        )

    @staticmethod
    def optimize_thresholds_from_samples(
        samples: Iterable[Dict[str, Any]],
        *,
        min_trades: int = 5,
        prob_grid: List[float] | None = None,
        quality_grid: List[float] | None = None,
    ) -> List[Dict[str, Any]]:
        prob_grid = prob_grid or [35, 40, 45, 50, 55, 60, 65, 70]
        quality_grid = quality_grid or [30, 35, 40, 45, 50, 55, 60]
        rows: List[Dict[str, Any]] = []
        sample_list = list(samples)
        for pth in prob_grid:
            for qth in quality_grid:
                selected = [
                    s for s in sample_list
                    if float(s.get("p_cal", 0.0)) >= pth
                    and float(s.get("setup_quality", 0.0)) >= qth
                    and float(s.get("expected_net_edge_r", s.get("expected_value", -999.0))) > 0.0
                ]
                n = len(selected)
                avg_net = sum(float(s.get("expected_net_edge_r", 0.0)) for s in selected) / n if n else 0.0
                avg_cost = sum(float(s.get("expected_round_trip_cost_bps", 0.0)) for s in selected) / n if n else 0.0
                score = avg_net * min(n, max(1, min_trades))
                rows.append({
                    "prob_threshold": pth,
                    "quality_threshold": qth,
                    "would_pass": n,
                    "avg_expected_net_edge_r": round(avg_net, 8),
                    "avg_expected_cost_bps": round(avg_cost, 4),
                    "optimization_score": round(score, 8),
                    "min_trades_met": n >= min_trades,
                })
        rows.sort(key=lambda r: (r["min_trades_met"], r["optimization_score"], r["would_pass"]), reverse=True)
        return rows

    @staticmethod
    def export_optimization_report(samples: Iterable[Dict[str, Any]], path: str | Path) -> Dict[str, Any]:
        sample_list = list(samples)
        rows = CostAwareMetaLabeler.optimize_thresholds_from_samples(sample_list)
        report = {
            "samples": len(sample_list),
            "recommended_thresholds": rows[:10],
            "note": "Recommendations are diagnostic only. Validate with walk-forward/backtest before changing live thresholds.",
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return report
