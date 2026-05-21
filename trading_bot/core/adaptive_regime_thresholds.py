"""
core/adaptive_regime_thresholds.py — Regime-specific threshold diagnostics
=========================================================================

This module ranks probability/setup-quality threshold pairs separately by
market regime.  It is diagnostic-only by default: it does not change live or
backtest decisions until the selected thresholds are validated out-of-sample.

The goal is not to increase trade count blindly.  The optimizer searches for
thresholds that preserve positive cost-adjusted expectancy while improving
signal density within each regime.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping
import json
import math
import statistics


@dataclass(frozen=True)
class RegimeThresholdCandidate:
    regime: str
    probability_threshold: float
    quality_threshold: float
    selected_count: int
    selected_rate_pct: float
    avg_expected_net_edge_r: float
    median_expected_net_edge_r: float
    avg_expected_cost_bps: float
    avg_probability: float
    avg_setup_quality: float
    optimization_score: float
    min_trades_met: bool
    status: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, float):
                d[k] = round(v, 8)
        return d


class AdaptiveRegimeThresholdOptimizer:
    """Threshold optimizer operating on SignalDensityMonitor samples."""

    DEFAULT_PROB_GRID = [30, 35, 40, 45, 50, 55, 60, 65, 70]
    DEFAULT_QUALITY_GRID = [25, 30, 35, 40, 45, 50, 55, 60]

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    @classmethod
    def _sample_regime(cls, sample: Mapping[str, Any]) -> str:
        regime = str(sample.get("regime", "UNKNOWN") or "UNKNOWN").upper()
        if regime in {"TREND", "TRENDING_MARKET"}:
            return "TRENDING"
        if regime in {"RANGE", "RANGING_MARKET"}:
            return "RANGING"
        return regime

    @classmethod
    def group_by_regime(cls, samples: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for sample in samples:
            row = dict(sample)
            regime = cls._sample_regime(row)
            row["regime"] = regime
            grouped.setdefault(regime, []).append(row)
        return grouped

    @classmethod
    def optimize_regime(
        cls,
        samples: Iterable[Mapping[str, Any]],
        *,
        regime: str,
        min_trades: int = 5,
        prob_grid: List[float] | None = None,
        quality_grid: List[float] | None = None,
        require_positive_net_edge: bool = True,
    ) -> List[RegimeThresholdCandidate]:
        sample_list = [dict(s) for s in samples]
        total = len(sample_list)
        if total == 0:
            return []
        prob_grid = prob_grid or cls.DEFAULT_PROB_GRID
        quality_grid = quality_grid or cls.DEFAULT_QUALITY_GRID
        rows: List[RegimeThresholdCandidate] = []

        for pth in prob_grid:
            for qth in quality_grid:
                selected: List[Dict[str, Any]] = []
                for sample in sample_list:
                    p = cls._as_float(sample.get("p_cal", sample.get("probability", 0.0)))
                    q = cls._as_float(sample.get("setup_quality", 0.0))
                    net = cls._as_float(sample.get("expected_net_edge_r", sample.get("expected_value", -999.0)), -999.0)
                    if p < pth or q < qth:
                        continue
                    if require_positive_net_edge and net <= 0.0:
                        continue
                    selected.append(sample)

                n = len(selected)
                if n:
                    nets = [cls._as_float(s.get("expected_net_edge_r", 0.0)) for s in selected]
                    costs = [cls._as_float(s.get("expected_round_trip_cost_bps", 0.0)) for s in selected]
                    probs = [cls._as_float(s.get("p_cal", 0.0)) for s in selected]
                    quals = [cls._as_float(s.get("setup_quality", 0.0)) for s in selected]
                    avg_net = statistics.fmean(nets)
                    med_net = statistics.median(nets)
                    avg_cost = statistics.fmean(costs)
                    avg_prob = statistics.fmean(probs)
                    avg_quality = statistics.fmean(quals)
                else:
                    avg_net = med_net = avg_cost = avg_prob = avg_quality = 0.0

                min_met = n >= min_trades
                # Score balances edge quality and sample density.  Do not reward
                # negative/zero sample sets.  Use sqrt(n) so huge count does not
                # dominate net expectancy.
                score = avg_net * math.sqrt(n) if n > 0 else 0.0
                if not min_met:
                    score *= 0.50
                status = "OK" if min_met and avg_net > 0 else ("LOW_SAMPLE" if n > 0 else "NO_EDGE")

                rows.append(RegimeThresholdCandidate(
                    regime=regime,
                    probability_threshold=float(pth),
                    quality_threshold=float(qth),
                    selected_count=n,
                    selected_rate_pct=(n / total * 100.0) if total else 0.0,
                    avg_expected_net_edge_r=avg_net,
                    median_expected_net_edge_r=med_net,
                    avg_expected_cost_bps=avg_cost,
                    avg_probability=avg_prob,
                    avg_setup_quality=avg_quality,
                    optimization_score=score,
                    min_trades_met=min_met,
                    status=status,
                ))

        rows.sort(key=lambda r: (r.status == "OK", r.optimization_score, r.selected_count), reverse=True)
        return rows

    @classmethod
    def build_report(
        cls,
        samples: Iterable[Mapping[str, Any]],
        *,
        min_trades_per_regime: int = 5,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        sample_list = [dict(s) for s in samples]
        grouped = cls.group_by_regime(sample_list)
        regimes: Dict[str, Any] = {}
        for regime, rows in sorted(grouped.items()):
            optimized = cls.optimize_regime(rows, regime=regime, min_trades=min_trades_per_regime)
            positive_net = [r for r in rows if cls._as_float(r.get("expected_net_edge_r", -999.0), -999.0) > 0.0]
            regimes[regime] = {
                "samples": len(rows),
                "positive_net_edge_samples": len(positive_net),
                "positive_net_edge_rate_pct": round((len(positive_net) / len(rows) * 100.0) if rows else 0.0, 6),
                "recommended_thresholds": [r.to_dict() for r in optimized[:top_n]],
                "best_threshold": optimized[0].to_dict() if optimized else None,
            }
        global_opt = cls.optimize_regime(sample_list, regime="GLOBAL", min_trades=max(min_trades_per_regime, 5))
        return {
            "mode": "diagnostic_only",
            "samples": len(sample_list),
            "min_trades_per_regime": min_trades_per_regime,
            "regimes": regimes,
            "global_best": global_opt[0].to_dict() if global_opt else None,
            "global_recommended_thresholds": [r.to_dict() for r in global_opt[:top_n]],
            "safety_note": "Do not enable adaptive thresholds in live trading until validated with purged walk-forward and cost-aware backtests.",
        }

    @classmethod
    def export_report(cls, samples: Iterable[Mapping[str, Any]], path: str | Path, **kwargs: Any) -> Dict[str, Any]:
        report = cls.build_report(samples, **kwargs)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return report
