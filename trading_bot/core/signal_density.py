"""
core/signal_density.py — Signal density and threshold calibration diagnostics
=============================================================================

This module does not change trading decisions.  It records where candidate
setups are filtered so threshold changes can be made from evidence rather than
by manually lowering confidence gates until more trades appear.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import math
import statistics


@dataclass
class SignalDensityMonitor:
    """Collects funnel diagnostics for the technical -> meta -> execution path."""

    meta_prob_threshold: float
    meta_quality_threshold: float
    output_path: str | Path = "data/signal_density_report.json"
    enabled: bool = True

    bars_evaluated: int = 0
    technical_candidates: int = 0
    technical_rejections: int = 0
    setup_quality_pass: int = 0
    setup_quality_fail: int = 0
    meta_probability_pass: int = 0
    meta_probability_fail: int = 0
    positive_ev_pass: int = 0
    positive_ev_fail: int = 0
    meta_accepted: int = 0
    pending_triggers_created: int = 0
    pending_triggers_filled: int = 0
    pending_triggers_expired: int = 0
    risk_blocked: int = 0
    opened_trades: int = 0
    closed_trades: int = 0

    probabilities: List[float] = field(default_factory=list)
    setup_qualities: List[float] = field(default_factory=list)
    expected_values: List[float] = field(default_factory=list)
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    accepted_samples: List[Dict[str, Any]] = field(default_factory=list)
    rejected_samples: List[Dict[str, Any]] = field(default_factory=list)

    def _inc_reason(self, reason: str) -> None:
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def observe_bar(self) -> None:
        if self.enabled:
            self.bars_evaluated += 1

    def observe_no_technical_candidate(self) -> None:
        if self.enabled:
            self.technical_rejections += 1
            self._inc_reason("no_technical_candidate")

    def observe_technical_candidate(self, *, side: str, tech_score: float, entry_type: Any) -> None:
        if not self.enabled:
            return
        self.technical_candidates += 1

    def observe_meta_decision(
        self,
        *,
        side: str,
        p_cal: float,
        setup_quality: float,
        tech_score: float,
        expected_value: float,
        is_tech_ok: bool,
        ranked: bool,
        accepted: bool,
        regime: str = "UNKNOWN",
    ) -> None:
        if not self.enabled:
            return
        p = self._as_float(p_cal, 50.0)
        q = self._as_float(setup_quality, 0.0)
        ev = self._as_float(expected_value, -999.0)

        self.probabilities.append(p)
        self.setup_qualities.append(q)
        self.expected_values.append(ev)

        if q >= self.meta_quality_threshold and is_tech_ok:
            self.setup_quality_pass += 1
        else:
            self.setup_quality_fail += 1
            self._inc_reason("quality_below_threshold")

        if p >= self.meta_prob_threshold:
            self.meta_probability_pass += 1
        else:
            self.meta_probability_fail += 1
            self._inc_reason("probability_below_threshold")

        if ranked or ev > 0.0:
            self.positive_ev_pass += 1
        else:
            self.positive_ev_fail += 1
            self._inc_reason("non_positive_expected_value")

        sample = {
            "side": side,
            "p_cal": round(p, 6),
            "setup_quality": round(q, 6),
            "tech_score": round(self._as_float(tech_score), 6),
            "expected_value": round(ev, 6),
            "regime": regime,
        }
        if accepted:
            self.meta_accepted += 1
            self.accepted_samples.append(sample)
        else:
            self.rejected_samples.append(sample)

    def observe_pending_created(self) -> None:
        if self.enabled:
            self.pending_triggers_created += 1

    def observe_pending_filled(self) -> None:
        if self.enabled:
            self.pending_triggers_filled += 1

    def observe_pending_expired(self) -> None:
        if self.enabled:
            self.pending_triggers_expired += 1
            self._inc_reason("pending_trigger_expired")

    def observe_risk_blocked(self) -> None:
        if self.enabled:
            self.risk_blocked += 1
            self._inc_reason("risk_engine_blocked")

    def observe_opened_trade(self) -> None:
        if self.enabled:
            self.opened_trades += 1

    def observe_closed_trade(self) -> None:
        if self.enabled:
            self.closed_trades += 1

    @staticmethod
    def _summary(values: List[float]) -> Dict[str, Any]:
        vals = [float(v) for v in values if not math.isnan(float(v)) and not math.isinf(float(v))]
        if not vals:
            return {"count": 0}
        vals_sorted = sorted(vals)
        def pct(p: float) -> float:
            idx = min(len(vals_sorted) - 1, max(0, int(round((p / 100.0) * (len(vals_sorted) - 1)))))
            return vals_sorted[idx]
        return {
            "count": len(vals),
            "min": round(vals_sorted[0], 6),
            "p10": round(pct(10), 6),
            "p25": round(pct(25), 6),
            "median": round(pct(50), 6),
            "p75": round(pct(75), 6),
            "p90": round(pct(90), 6),
            "max": round(vals_sorted[-1], 6),
            "mean": round(statistics.fmean(vals), 6),
        }

    def _buckets(self, values: List[float], edges: List[float]) -> Dict[str, int]:
        buckets: Dict[str, int] = {}
        if not edges:
            return buckets
        sorted_edges = sorted(edges)
        labels = []
        prev = None
        for edge in sorted_edges:
            labels.append((prev, edge))
            prev = edge
        labels.append((prev, None))
        for low, high in labels:
            if low is None:
                key = f"< {high:g}"
            elif high is None:
                key = f">= {low:g}"
            else:
                key = f"{low:g}-{high:g}"
            buckets[key] = 0
        for v in values:
            x = self._as_float(v)
            for low, high in labels:
                if low is None and x < high:
                    buckets[f"< {high:g}"] += 1
                    break
                if high is None and x >= low:
                    buckets[f">= {low:g}"] += 1
                    break
                if low is not None and high is not None and low <= x < high:
                    buckets[f"{low:g}-{high:g}"] += 1
                    break
        return buckets

    def threshold_sweep(self) -> List[Dict[str, Any]]:
        """Counts how many observed technical candidates would pass alternative gates."""
        rows = []
        prob_grid = [40, 45, 50, 55, 60, 65, 70]
        qual_grid = [40, 45, 50, 55, 60]
        samples = list(zip(self.probabilities, self.setup_qualities, self.expected_values))
        for prob_th in prob_grid:
            for quality_th in qual_grid:
                pass_count = sum(1 for p, q, ev in samples if p >= prob_th and q >= quality_th and ev > 0.0)
                rows.append({
                    "prob_threshold": prob_th,
                    "quality_threshold": quality_th,
                    "would_pass": pass_count,
                    "pass_rate_pct": round((pass_count / len(samples) * 100.0) if samples else 0.0, 4),
                })
        return rows

    def build_report(self) -> Dict[str, Any]:
        funnel = {
            "bars_evaluated": self.bars_evaluated,
            "technical_candidates": self.technical_candidates,
            "technical_candidate_rate_pct": round((self.technical_candidates / self.bars_evaluated * 100.0) if self.bars_evaluated else 0.0, 4),
            "meta_accepted": self.meta_accepted,
            "meta_acceptance_rate_pct": round((self.meta_accepted / self.technical_candidates * 100.0) if self.technical_candidates else 0.0, 4),
            "pending_triggers_created": self.pending_triggers_created,
            "pending_triggers_filled": self.pending_triggers_filled,
            "pending_fill_rate_pct": round((self.pending_triggers_filled / self.pending_triggers_created * 100.0) if self.pending_triggers_created else 0.0, 4),
            "pending_triggers_expired": self.pending_triggers_expired,
            "risk_blocked": self.risk_blocked,
            "opened_trades": self.opened_trades,
            "closed_trades": self.closed_trades,
        }
        return {
            "thresholds": {
                "meta_probability_threshold": self.meta_prob_threshold,
                "meta_quality_threshold": self.meta_quality_threshold,
                "positive_ev_required": True,
            },
            "funnel": funnel,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items(), key=lambda kv: kv[1], reverse=True)),
            "probability_distribution": self._summary(self.probabilities),
            "probability_buckets": self._buckets(self.probabilities, [40, 45, 50, 55, 60, 65, 70]),
            "setup_quality_distribution": self._summary(self.setup_qualities),
            "setup_quality_buckets": self._buckets(self.setup_qualities, [40, 45, 50, 55, 60, 70, 80]),
            "expected_value_distribution": self._summary(self.expected_values),
            "threshold_sweep": self.threshold_sweep(),
            "sample_rejected_setups": self.rejected_samples[:25],
            "sample_accepted_setups": self.accepted_samples[:25],
            "diagnostic_interpretation": self._interpret(funnel),
        }

    def _interpret(self, funnel: Dict[str, Any]) -> List[str]:
        notes: List[str] = []
        if funnel["technical_candidates"] == 0:
            notes.append("No technical candidates were generated. Investigate rule engine thresholds before changing ML thresholds.")
        elif funnel["meta_accepted"] == 0:
            notes.append("Technical candidates exist but the meta layer accepts none. Inspect calibrated probabilities, setup quality and EV gates.")
        elif funnel["opened_trades"] < funnel["meta_accepted"]:
            notes.append("Meta layer accepts more setups than are opened. Inspect breakout TTL and risk sizing blocks.")
        if self.probabilities and max(self.probabilities) < self.meta_prob_threshold:
            notes.append("All calibrated probabilities are below the configured probability threshold. The model/calibrator is very conservative.")
        if self.setup_qualities and max(self.setup_qualities) < self.meta_quality_threshold:
            notes.append("All setup quality scores are below threshold. Technical quality gate is the bottleneck.")
        if self.positive_ev_fail > self.positive_ev_pass:
            notes.append("Most candidates are non-positive EV after calibration and RR assumptions. Lowering thresholds alone may increase negative expectancy trades.")
        return notes

    def export(self, output_path: Optional[str | Path] = None) -> Dict[str, Any]:
        report = self.build_report()
        path = Path(output_path or self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"  [SignalDensity] Report exported -> {path}")
        return report
