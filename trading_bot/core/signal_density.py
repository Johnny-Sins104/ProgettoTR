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
    expected_net_edges: List[float] = field(default_factory=list)
    expected_costs_bps: List[float] = field(default_factory=list)
    cost_to_edge_ratios: List[float] = field(default_factory=list)
    cost_aware_pass: int = 0
    cost_aware_fail: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    accepted_samples: List[Dict[str, Any]] = field(default_factory=list)
    rejected_samples: List[Dict[str, Any]] = field(default_factory=list)
    setup_archetype_counts: Dict[str, int] = field(default_factory=dict)
    structure_scores: List[float] = field(default_factory=list)
    structure_reason_counts: Dict[str, int] = field(default_factory=dict)
    archetype_score_samples: Dict[str, List[float]] = field(default_factory=dict)
    market_structure_available_count: int = 0
    market_structure_missing_count: int = 0
    archetype_missing_feature_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    archetype_gate_fail_counts: Dict[str, int] = field(default_factory=dict)
    ai_prediction_source_counts: Dict[str, int] = field(default_factory=dict)
    ai_neutral_probability_count: int = 0
    ai_not_ready_count: int = 0
    ai_feature_missing_counts: Dict[str, int] = field(default_factory=dict)


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
        expected_net_edge: float | None = None,
        expected_round_trip_cost_bps: float | None = None,
        cost_to_edge_ratio: float | None = None,
        cost_aware_accepted: bool | None = None,
        is_tech_ok: bool,
        ranked: bool,
        accepted: bool,
        regime: str = "UNKNOWN",
        setup_archetype: str = "UNKNOWN",
        structure_score: float | None = None,
        edge_adjustment_r: float | None = None,
        structure_components: Dict[str, Any] | None = None,
        structure_reasons: List[str] | None = None,
        rejection_reason: str | None = None,
        ai_diagnostics: Dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        p = self._as_float(p_cal, 50.0)
        q = self._as_float(setup_quality, 0.0)
        ev = self._as_float(expected_value, -999.0)
        net_ev = self._as_float(expected_net_edge, ev)
        cost_bps = self._as_float(expected_round_trip_cost_bps, 0.0)
        cte = self._as_float(cost_to_edge_ratio, 0.0)
        ss = self._as_float(structure_score, 0.0)
        archetype = str(setup_archetype or "UNKNOWN")
        self.setup_archetype_counts[archetype] = self.setup_archetype_counts.get(archetype, 0) + 1
        ai_diag = dict(ai_diagnostics or {})
        ai_source = str(ai_diag.get("prediction_source", "unknown"))
        self.ai_prediction_source_counts[ai_source] = self.ai_prediction_source_counts.get(ai_source, 0) + 1
        if abs(p - 50.0) < 1e-9:
            self.ai_neutral_probability_count += 1
        if ai_diag.get("model_ready") is False:
            self.ai_not_ready_count += 1
        for feat in ai_diag.get("missing_features", []) or []:
            feat_s = str(feat)
            self.ai_feature_missing_counts[feat_s] = self.ai_feature_missing_counts.get(feat_s, 0) + 1
        self.structure_scores.append(ss)
        for reason in structure_reasons or []:
            reason_key = str(reason or "unknown_structure_reason")
            self.structure_reason_counts[reason_key] = self.structure_reason_counts.get(reason_key, 0) + 1
        components = structure_components or {}
        if self._as_float(components.get("runtime_market_structure_available", 0.0), 0.0) >= 1.0:
            self.market_structure_available_count += 1
        else:
            self.market_structure_missing_count += 1
        for key, value in components.items():
            key_s = str(key)
            if key_s.startswith("score_"):
                archetype_name = key_s.replace("score_", "", 1)
                self.archetype_score_samples.setdefault(archetype_name, []).append(self._as_float(value, 0.0))
            elif key_s.startswith("missing_count_"):
                archetype_name = key_s.replace("missing_count_", "", 1)
                n_missing = int(round(self._as_float(value, 0.0)))
                bucket = self.archetype_missing_feature_counts.setdefault(archetype_name, {})
                bucket[str(n_missing)] = bucket.get(str(n_missing), 0) + 1

        self.probabilities.append(p)
        self.setup_qualities.append(q)
        self.expected_values.append(ev)
        self.expected_net_edges.append(net_ev)
        self.expected_costs_bps.append(cost_bps)
        self.cost_to_edge_ratios.append(cte)

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

        if cost_aware_accepted is None:
            cost_aware_accepted = net_ev > 0.0
        if cost_aware_accepted:
            self.cost_aware_pass += 1
        else:
            self.cost_aware_fail += 1
            self._inc_reason("non_positive_cost_adjusted_ev")

        if rejection_reason:
            reason_key = str(rejection_reason)
            self._inc_reason(reason_key)
            if reason_key.startswith("archetype_gate_"):
                self.archetype_gate_fail_counts[archetype] = self.archetype_gate_fail_counts.get(archetype, 0) + 1

        sample = {
            "side": side,
            "p_cal": round(p, 6),
            "setup_quality": round(q, 6),
            "tech_score": round(self._as_float(tech_score), 6),
            "expected_value": round(ev, 6),
            "expected_net_edge_r": round(net_ev, 6),
            "expected_round_trip_cost_bps": round(cost_bps, 6),
            "cost_to_edge_ratio": round(cte, 6),
            "cost_aware_accepted": bool(cost_aware_accepted),
            "regime": regime,
            "setup_archetype": archetype,
            "structure_score": round(ss, 6),
            "edge_adjustment_r": round(self._as_float(edge_adjustment_r, 0.0), 6),
            "structure_reasons": list(structure_reasons or []),
            "structure_components": dict(structure_components or {}),
            "rejection_reason": str(rejection_reason or ""),
            "ai_diagnostics": ai_diag,
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

    def setup_archetype_diagnostics(self) -> Dict[str, Any]:
        """Explain archetype dominance and inactive setup families."""
        diagnostics: Dict[str, Any] = {}
        total = max(1, self.technical_candidates)
        for archetype, values in sorted(self.archetype_score_samples.items()):
            vals = [self._as_float(v, 0.0) for v in values]
            diagnostics[archetype] = {
                "score_distribution": self._summary(vals),
                "count_score_gte_20": sum(1 for v in vals if v >= 20.0),
                "count_score_gte_40": sum(1 for v in vals if v >= 40.0),
                "count_score_gte_60": sum(1 for v in vals if v >= 60.0),
                "activation_rate_gte_40_pct": round((sum(1 for v in vals if v >= 40.0) / total) * 100.0, 4),
            }
        selected_total = sum(self.setup_archetype_counts.values()) or 1
        dominance = {
            k: round(v / selected_total * 100.0, 4)
            for k, v in sorted(self.setup_archetype_counts.items(), key=lambda kv: kv[1], reverse=True)
        }
        return {
            "selected_archetype_counts": dict(sorted(self.setup_archetype_counts.items(), key=lambda kv: kv[1], reverse=True)),
            "selected_archetype_share_pct": dominance,
            "candidate_score_diagnostics": diagnostics,
            "structure_reason_counts": dict(sorted(self.structure_reason_counts.items(), key=lambda kv: kv[1], reverse=True)),
            "runtime_market_structure_feature_audit": {
                "available_count": self.market_structure_available_count,
                "missing_count": self.market_structure_missing_count,
                "available_rate_pct": round(
                    self.market_structure_available_count / max(1, self.market_structure_available_count + self.market_structure_missing_count) * 100.0,
                    4,
                ),
                "missing_count_distribution_by_archetype": dict(sorted(self.archetype_missing_feature_counts.items())),
            },
            "archetype_gate_fail_counts": dict(sorted(self.archetype_gate_fail_counts.items(), key=lambda kv: kv[1], reverse=True)),
            "interpretation": self._interpret_archetypes(dominance, diagnostics),
        }

    def _interpret_archetypes(self, dominance: Dict[str, float], diagnostics: Dict[str, Any]) -> List[str]:
        notes: List[str] = []
        if dominance:
            top_name, top_share = next(iter(dominance.items()))
            if top_share >= 80.0:
                notes.append(
                    f"Archetype concentration is high: {top_name} accounts for {top_share:.2f}% of selected technical candidates."
                )
        total_ms = self.market_structure_available_count + self.market_structure_missing_count
        if total_ms and self.market_structure_available_count == 0:
            notes.append("Runtime market-structure features are missing on every technical candidate; enrich the backtest dataframe before setup evaluation.")
        elif total_ms and self.market_structure_available_count / max(1, total_ms) < 0.8:
            notes.append("Runtime market-structure feature coverage is partial; inspect DataCollector/backtest feature propagation.")
        for name, row in diagnostics.items():
            if row.get("count_score_gte_40", 0) == 0:
                notes.append(f"{name} never reached structure score >= 40; inspect missing source features or thresholds.")
        return notes

    def threshold_sweep(self) -> List[Dict[str, Any]]:
        """Counts how many observed technical candidates would pass alternative gates."""
        rows = []
        prob_grid = [40, 45, 50, 55, 60, 65, 70]
        qual_grid = [40, 45, 50, 55, 60]
        samples = list(zip(self.probabilities, self.setup_qualities, self.expected_net_edges))
        for prob_th in prob_grid:
            for quality_th in qual_grid:
                pass_count = sum(1 for p, q, net_ev in samples if p >= prob_th and q >= quality_th and net_ev > 0.0)
                rows.append({
                    "prob_threshold": prob_th,
                    "quality_threshold": quality_th,
                    "would_pass": pass_count,
                    "pass_rate_pct": round((pass_count / len(samples) * 100.0) if samples else 0.0, 4),
                })
        return rows


    def cost_aware_threshold_optimization(self) -> List[Dict[str, Any]]:
        """Ranks threshold combinations by estimated net edge, not raw trade count."""
        try:
            from core.cost_aware_meta import CostAwareMetaLabeler
        except Exception:
            return []
        samples = self.accepted_samples + self.rejected_samples
        return CostAwareMetaLabeler.optimize_thresholds_from_samples(samples, min_trades=3)[:25]

    def adaptive_regime_threshold_report(self) -> Dict[str, Any]:
        """Optimizes thresholds separately per regime using cost-adjusted edge."""
        try:
            from config import Config
            from core.adaptive_regime_thresholds import AdaptiveRegimeThresholdOptimizer
        except Exception:
            return {}
        samples = self.accepted_samples + self.rejected_samples
        if not getattr(Config, "ADAPTIVE_REGIME_THRESHOLDS_ENABLED", True):
            return {}
        return AdaptiveRegimeThresholdOptimizer.build_report(
            samples,
            min_trades_per_regime=int(getattr(Config, "ADAPTIVE_REGIME_MIN_TRADES", 3)),
            top_n=5,
        )

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
            "cost_aware_pass": self.cost_aware_pass,
            "cost_aware_fail": self.cost_aware_fail,
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
            "structure_score_distribution": self._summary(self.structure_scores),
            "setup_archetype_counts": dict(sorted(self.setup_archetype_counts.items(), key=lambda kv: kv[1], reverse=True)),
            "setup_archetype_diagnostics": self.setup_archetype_diagnostics(),
            "expected_value_distribution": self._summary(self.expected_values),
            "expected_net_edge_distribution": self._summary(self.expected_net_edges),
            "expected_cost_bps_distribution": self._summary(self.expected_costs_bps),
            "cost_to_edge_ratio_distribution": self._summary(self.cost_to_edge_ratios),
            "threshold_sweep": self.threshold_sweep(),
            "cost_aware_threshold_optimization": self.cost_aware_threshold_optimization(),
            "adaptive_regime_threshold_optimization": self.adaptive_regime_threshold_report(),
            "ai_prediction_audit": {
                "prediction_source_counts": dict(sorted(self.ai_prediction_source_counts.items(), key=lambda kv: kv[1], reverse=True)),
                "neutral_probability_count": self.ai_neutral_probability_count,
                "neutral_probability_rate_pct": round((self.ai_neutral_probability_count / len(self.probabilities) * 100.0) if self.probabilities else 0.0, 4),
                "model_not_ready_count": self.ai_not_ready_count,
                "top_missing_features": dict(sorted(self.ai_feature_missing_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]),
            },
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
        if self.cost_aware_fail > self.cost_aware_pass:
            notes.append("Most candidates do not survive expected execution costs. Optimize thresholds on net expectancy, not trade count.")
        if funnel["technical_candidates"] and funnel["meta_acceptance_rate_pct"] >= 80.0:
            notes.append("Meta acceptance rate is very high. Apply archetype-conditioned thresholds or the meta layer is not selective enough.")
        return notes

    def export(self, output_path: Optional[str | Path] = None) -> Dict[str, Any]:
        report = self.build_report()
        path = Path(output_path or self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        adaptive_report = report.get("adaptive_regime_threshold_optimization") or {}
        if adaptive_report:
            try:
                from config import Config
                adaptive_path = Path(getattr(Config, "ADAPTIVE_REGIME_THRESHOLD_REPORT_PATH", "data/adaptive_regime_threshold_report.json"))
                adaptive_path.parent.mkdir(parents=True, exist_ok=True)
                with adaptive_path.open("w", encoding="utf-8") as af:
                    json.dump(adaptive_report, af, indent=2)
                print(f"  [AdaptiveRegimeThresholds] Report exported -> {adaptive_path}")
            except Exception:
                pass
        print(f"  [SignalDensity] Report exported -> {path}")
        return report
