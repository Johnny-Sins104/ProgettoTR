"""Prompt 29.4.4s-1 probability compression / zero-trade gate attribution.

Diagnostic-only guardrail for the large-window failure mode where the backtest
still finds technical and cost-aware candidates, but the calibrated probability
distribution is compressed below the operational gate so meta_accepted collapses
to zero.  This module does not lower thresholds and does not enable trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from config import Config

REPORT_NAME = "probability_compression_diagnostic_report.json"
PROMPT_ID = "29.4.4s-1"
READY_DECISION = "PROBABILITY_COMPRESSION_DIAGNOSTIC_READY"
KEEP_DECISION = "KEEP_DIAGNOSTIC_PROBABILITY_COMPRESSION"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass(frozen=True)
class ProbabilityCompressionDiagnosticSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    labels: tuple[str, ...] = ("10k", "12k", "15k", "18k", "20k", "50k", "100k")
    gate_min_probability: float = 52.0
    compression_max_probability: float = 50.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "ProbabilityCompressionDiagnosticSettings":
        labels_raw = str(getattr(cfg, "PROBABILITY_COMPRESSION_LABELS", "10k,12k,15k,18k,20k,50k,100k"))
        labels = tuple(x.strip() for x in labels_raw.replace(";", ",").split(",") if x.strip())
        return cls(
            data_dir=str(getattr(cfg, "DATA_DIR", "data") or "data"),
            report_name=str(getattr(cfg, "PROBABILITY_COMPRESSION_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            labels=labels or cls.labels,
            gate_min_probability=_safe_float(getattr(cfg, "PROBABILITY_COMPRESSION_GATE_MIN_PROBABILITY", 52.0), 52.0),
            compression_max_probability=_safe_float(getattr(cfg, "PROBABILITY_COMPRESSION_MAX_PROBABILITY", 50.0), 50.0),
        )


def _extract(label: str, report: dict[str, Any], settings: ProbabilityCompressionDiagnosticSettings) -> dict[str, Any]:
    funnel = report.get("funnel") if isinstance(report.get("funnel"), dict) else {}
    dist = report.get("probability_distribution") if isinstance(report.get("probability_distribution"), dict) else {}
    opt = report.get("cost_aware_threshold_optimization")
    top_opt = opt[0] if isinstance(opt, list) and opt and isinstance(opt[0], dict) else {}
    max_probability = _safe_float(dist.get("max"), 0.0)
    cost_aware_pass = _safe_int(funnel.get("cost_aware_pass"), 0)
    meta_accepted = _safe_int(funnel.get("meta_accepted"), 0)
    opened_trades = _safe_int(funnel.get("opened_trades"), 0)
    compression_detected = (
        cost_aware_pass > 0
        and meta_accepted == 0
        and max_probability <= max(settings.compression_max_probability, settings.gate_min_probability)
    )
    impossible_gate = max_probability < settings.gate_min_probability
    return {
        "label": label,
        "bars_evaluated": _safe_int(funnel.get("bars_evaluated"), 0),
        "technical_candidates": _safe_int(funnel.get("technical_candidates"), 0),
        "cost_aware_pass": cost_aware_pass,
        "cost_aware_fail": _safe_int(funnel.get("cost_aware_fail"), 0),
        "meta_accepted": meta_accepted,
        "pending_triggers_created": _safe_int(funnel.get("pending_triggers_created"), 0),
        "opened_trades": opened_trades,
        "max_probability": max_probability,
        "median_probability": _safe_float(dist.get("median"), 0.0),
        "p90_probability": _safe_float(dist.get("p90"), 0.0),
        "gate_min_probability": settings.gate_min_probability,
        "probability_gate_impossible": bool(impossible_gate),
        "compression_detected": bool(compression_detected),
        "best_cost_aware_threshold": {
            "prob_threshold": _safe_float(top_opt.get("prob_threshold"), 0.0),
            "quality_threshold": _safe_float(top_opt.get("quality_threshold"), 0.0),
            "would_pass": _safe_int(top_opt.get("would_pass"), 0),
            "avg_expected_net_edge_r": _safe_float(top_opt.get("avg_expected_net_edge_r"), 0.0),
        },
    }


def build_probability_compression_report(
    *,
    settings: ProbabilityCompressionDiagnosticSettings | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    settings = settings or ProbabilityCompressionDiagnosticSettings.from_config()
    data_dir = Path(settings.data_dir)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for label in settings.labels:
        path = data_dir / f"signal_density_{label}.json"
        if not path.exists():
            missing.append(label)
            continue
        report = _read_json(path)
        if report:
            rows.append(_extract(label, report, settings))

    compression_rows = [r for r in rows if r.get("compression_detected")]
    impossible_rows = [r for r in rows if r.get("probability_gate_impossible")]
    status = "WARN" if compression_rows else "PASS"
    payload = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": KEEP_DECISION if compression_rows else READY_DECISION,
        "ts": utc_now_iso(),
        "data_dir": str(data_dir),
        "labels_checked": list(settings.labels),
        "missing_labels": missing,
        "gate_min_probability": settings.gate_min_probability,
        "compression_max_probability": settings.compression_max_probability,
        "rows": rows,
        "compression_detected": bool(compression_rows),
        "compression_labels": [r["label"] for r in compression_rows],
        "probability_gate_impossible_labels": [r["label"] for r in impossible_rows],
        "safety_note": "Diagnostic only: this report must not lower thresholds or force trades.",
    }
    if write_report:
        out = data_dir / settings.report_name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        payload["report"] = str(out)
    return payload
