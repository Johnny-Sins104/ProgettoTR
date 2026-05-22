"""Prompt 29.4.2 paper signal-density diagnostics.

This module is diagnostic-only.  It does not alter strategy decisions, sizing,
risk, broker state, or live/testnet behavior.  It classifies why each paper scan
became NO_SIGNAL / SIGNAL_DETECTED and writes an operator report that can be used
for conservative signal-density analysis.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import json
import math
import re

import pandas as pd

from config import Config


DIAGNOSTIC_EVENT_TYPE = "SIGNAL_DIAGNOSTIC"


@dataclass(frozen=True)
class DiagnosticThresholds:
    meta_prob_threshold: float
    meta_quality_threshold: float
    trending_threshold: float
    ranging_threshold: float
    exploratory_meta_prob_threshold: float
    exploratory_ranging_meta_prob_threshold: float
    exploratory_min_setup_quality: float
    exploratory_enabled: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100.0


def thresholds_from_config() -> DiagnosticThresholds:
    return DiagnosticThresholds(
        meta_prob_threshold=safe_float(getattr(Config, "META_PROB_THRESHOLD", 55.0), 55.0),
        meta_quality_threshold=safe_float(getattr(Config, "META_QUALITY_THRESHOLD", 50.0), 50.0),
        trending_threshold=safe_float(getattr(Config, "TRENDING_THRESHOLD", 60), 60.0),
        ranging_threshold=safe_float(getattr(Config, "RANGING_THRESHOLD", 30), 30.0),
        exploratory_meta_prob_threshold=safe_float(getattr(Config, "PAPER_EXPLORATORY_META_PROB_THRESHOLD", 48.0), 48.0),
        exploratory_ranging_meta_prob_threshold=safe_float(getattr(Config, "PAPER_EXPLORATORY_RANGING_META_PROB_THRESHOLD", 45.0), 45.0),
        exploratory_min_setup_quality=safe_float(getattr(Config, "PAPER_EXPLORATORY_MIN_SETUP_QUALITY", 60.0), 60.0),
        exploratory_enabled=bool(getattr(Config, "PAPER_EXPLORATORY_SIGNAL_ANALYSIS", True)),
    )


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _dominant_reason_from_engine(
    *,
    final_verdict: str,
    technical_verdict: str,
    tech_score: float,
    regime: str,
    row: Any,
    conf: dict[str, Any],
    conf_comb: str,
    duplicate_candle: bool = False,
) -> tuple[str, str]:
    """Return (dominant_filter, diagnostic_reason)."""
    if duplicate_candle:
        return "DUPLICATE_CANDLE", "accepted setup already processed for this candle"

    if final_verdict in {"BUY", "SELL"}:
        return "ACCEPTED", "signal accepted by current strategy gates"

    regime_u = str(regime or "RANGING").upper()
    threshold = thresholds_from_config().trending_threshold if regime_u == "TRENDING" else thresholds_from_config().ranging_threshold
    abs_score = abs(float(tech_score or 0.0))

    if abs_score < threshold:
        return "TECH_SCORE_LOW", f"abs_tech_score {abs_score:.2f} below {threshold:.2f} {regime_u} threshold"

    comb = str(conf_comb or "")
    if "MTF_Filtered" in comb:
        return "MTF_FILTERED", comb
    if "Meta_Filtered" in comb:
        ai_prob = safe_float(conf.get("ai_prob"), 0.0)
        setup_quality = safe_float(conf.get("setup_quality"), 0.0)
        th = thresholds_from_config()
        if ai_prob < th.meta_prob_threshold:
            return "META_PROB_LOW", f"ai_prob {ai_prob:.2f} below {th.meta_prob_threshold:.2f}"
        if setup_quality < th.meta_quality_threshold:
            return "SETUP_QUALITY_LOW", f"setup_quality {setup_quality:.2f} below {th.meta_quality_threshold:.2f}"
        return "META_FILTERED", comb

    close = safe_float(row.get("Close"), 0.0) if hasattr(row, "get") else 0.0
    ema_200 = safe_float(row.get("ema_200"), 0.0) if hasattr(row, "get") else 0.0
    ema_400 = safe_float(row.get("ema_400"), 0.0) if hasattr(row, "get") else 0.0
    range_pos_400 = safe_float(row.get("range_pos_400"), 0.5) if hasattr(row, "get") else 0.5

    intended_side = "BUY" if float(tech_score or 0.0) >= 0 else "SELL"
    if regime_u == "RANGING":
        if intended_side == "BUY" and range_pos_400 > 0.6:
            return "RANGE_POSITION_FILTERED", f"BUY blocked: range_pos_400 {range_pos_400:.3f} > 0.600"
        if intended_side == "SELL" and range_pos_400 < 0.4:
            return "RANGE_POSITION_FILTERED", f"SELL blocked: range_pos_400 {range_pos_400:.3f} < 0.400"
    if regime_u == "TRENDING":
        if intended_side == "BUY" and ema_200 <= ema_400:
            return "TREND_ALIGNMENT_FILTERED", "BUY blocked: ema_200 <= ema_400"
        if intended_side == "SELL" and ema_200 >= ema_400:
            return "TREND_ALIGNMENT_FILTERED", "SELL blocked: ema_200 >= ema_400"

    ema_1h_200 = safe_float(row.get("ema_1h_200"), 0.0) if hasattr(row, "get") else 0.0
    if ema_1h_200 > 0:
        if intended_side == "BUY" and close <= ema_1h_200:
            return "MTF_FILTERED", "BUY blocked: close <= ema_1h_200"
        if intended_side == "SELL" and close >= ema_1h_200:
            return "MTF_FILTERED", "SELL blocked: close >= ema_1h_200"

    if str(technical_verdict or "HOLD") in {"BUY", "SELL"}:
        return "POST_TECH_FILTERED", comb or "technical candidate rejected by later gate"
    return "NO_TECHNICAL_CANDIDATE", "technical rules did not create BUY/SELL candidate"


def build_signal_diagnostic(
    *,
    symbol: str,
    df: pd.DataFrame,
    final_verdict: str,
    final_score: Any,
    confidence: dict[str, Any] | None,
    entry_type: Any,
    conf_verdict: Any,
    conf_comb: Any,
    cycle_id: str,
    candle_ts: str,
    last_price: float,
    duplicate_candle: bool = False,
) -> dict[str, Any]:
    """Build one diagnostic event payload for a paper scan."""
    conf = confidence if isinstance(confidence, dict) else {}
    row = df.iloc[-1]
    regime = str(row.get("market_regime", "RANGING")) if hasattr(row, "get") else "RANGING"

    # Re-run only the cheap technical stage for explanation.  This does not
    # modify trading decisions and intentionally avoids an extra AI prediction.
    technical_verdict = "UNKNOWN"
    technical_score = safe_float(conf.get("tech_score"), safe_float(final_score, 0.0))
    technical_combination = ""
    technical_conf: dict[str, Any] = {}
    try:
        from core.engine import DecisionEngine

        technical_verdict, raw_score, technical_conf, _entry, _cv, technical_combination = DecisionEngine()._evaluate_score(df)
        technical_score = safe_float(raw_score, technical_score)
    except Exception as exc:
        technical_combination = f"technical_stage_unavailable:{exc.__class__.__name__}"

    thresholds = thresholds_from_config()
    final_v = str(final_verdict or "HOLD").upper()
    technical_v = str(technical_verdict or "HOLD").upper()
    dominant_filter, reason = _dominant_reason_from_engine(
        final_verdict=final_v,
        technical_verdict=technical_v,
        tech_score=technical_score,
        regime=regime,
        row=row,
        conf=conf,
        conf_comb=str(conf_comb or ""),
        duplicate_candle=duplicate_candle,
    )
    ai_prob = safe_float(conf.get("ai_prob"), 0.0)
    setup_quality = safe_float(conf.get("setup_quality"), 0.0)
    active_threshold = thresholds.trending_threshold if str(regime).upper() == "TRENDING" else thresholds.ranging_threshold
    intended_side = technical_v if technical_v in {"BUY", "SELL"} else ("BUY" if technical_score >= active_threshold else "SELL" if technical_score <= -active_threshold else "HOLD")

    regular_gate_missing = {
        "tech_score_gap": round(max(0.0, active_threshold - abs(technical_score)), 6),
        "meta_prob_gap": round(max(0.0, thresholds.meta_prob_threshold - ai_prob), 6),
        "setup_quality_gap": round(max(0.0, thresholds.meta_quality_threshold - setup_quality), 6),
    }
    exploratory_prob_threshold = thresholds.exploratory_ranging_meta_prob_threshold if str(regime).upper() == "RANGING" else thresholds.exploratory_meta_prob_threshold
    exploratory_candidate = bool(
        thresholds.exploratory_enabled
        and technical_v in {"BUY", "SELL"}
        and ai_prob >= exploratory_prob_threshold
        and setup_quality >= thresholds.exploratory_min_setup_quality
        and dominant_filter in {"META_PROB_LOW", "META_FILTERED", "POST_TECH_FILTERED"}
    )
    near_candidate = bool(
        technical_v in {"BUY", "SELL"}
        or abs(technical_score) >= max(0.0, active_threshold - 5.0)
        or setup_quality >= thresholds.meta_quality_threshold
    )

    return {
        "event_type": DIAGNOSTIC_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": candle_ts,
        "last_price": round(float(last_price), 8),
        "final_verdict": final_v,
        "final_score": safe_int(final_score, 0),
        "entry_type": entry_type,
        "confidence_verdict": conf_verdict,
        "confidence_combination": conf_comb,
        "technical_verdict": technical_v,
        "technical_score": round(float(technical_score), 6),
        "technical_combination": technical_combination,
        "technical_confidence": technical_conf,
        "intended_side": intended_side,
        "regime": regime,
        "dominant_filter": dominant_filter,
        "diagnostic_reason": reason,
        "ai_prob": round(ai_prob, 8),
        "setup_quality": round(setup_quality, 8),
        "thresholds": {
            "active_score_threshold": active_threshold,
            "meta_prob_threshold": thresholds.meta_prob_threshold,
            "meta_quality_threshold": thresholds.meta_quality_threshold,
            "exploratory_meta_prob_threshold": exploratory_prob_threshold,
            "exploratory_min_setup_quality": thresholds.exploratory_min_setup_quality,
        },
        "regular_gate_missing": regular_gate_missing,
        "near_candidate": near_candidate,
        "exploratory_candidate": exploratory_candidate,
        "diagnostic_only": True,
        "strategy_changed": False,
        "duplicate_candle": bool(duplicate_candle),
        "ts": utc_now_iso(),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                out.append(payload)
        except Exception:
            continue
    return out


CYCLE_ID_RE = re.compile(r"pc_(\d+)_[0-9a-fA-F]+")


def cycle_seq(cycle_id: Any) -> int | None:
    m = CYCLE_ID_RE.fullmatch(str(cycle_id or ""))
    return int(m.group(1)) if m else None


def _top_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[float, float, float, int]:
        return (
            safe_float(row.get("setup_quality"), 0.0),
            safe_float(row.get("ai_prob"), 0.0),
            abs(safe_float(row.get("technical_score"), 0.0)),
            safe_int(cycle_seq(row.get("cycle_id")), 0),
        )

    return sorted(rows, key=key, reverse=True)[:limit]


def build_signal_diagnostics_report(data_dir: str | Path, *, top_n: int = 25) -> dict[str, Any]:
    data_path = Path(data_dir)
    events_path = data_path / "paper_events.jsonl"
    events = read_jsonl(events_path)
    diagnostics = [e for e in events if str(e.get("event_type") or "").upper() == DIAGNOSTIC_EVENT_TYPE]
    event_counts = Counter(str(e.get("event_type") or "").upper() for e in events)
    filter_counts = Counter(str(e.get("dominant_filter") or "UNKNOWN") for e in diagnostics)
    by_asset: dict[str, dict[str, Any]] = {}
    by_asset_raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in diagnostics:
        by_asset_raw[str(e.get("symbol") or "UNKNOWN")].append(e)

    for symbol, rows in sorted(by_asset_raw.items()):
        filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in rows)
        meta_rows = [r for r in rows if safe_float(r.get("setup_quality"), 0.0) > 0]
        near_rows = [r for r in rows if _bool(r.get("near_candidate"))]
        exploratory_rows = [r for r in rows if _bool(r.get("exploratory_candidate"))]
        ai_vals = [safe_float(r.get("ai_prob"), 0.0) for r in meta_rows]
        q_vals = [safe_float(r.get("setup_quality"), 0.0) for r in meta_rows]
        tech_vals = [abs(safe_float(r.get("technical_score"), 0.0)) for r in rows]
        by_asset[symbol] = {
            "scans": len(rows),
            "dominant_filters": dict(filters.most_common()),
            "near_candidates": len(near_rows),
            "exploratory_candidates": len(exploratory_rows),
            "meta_reached": len(meta_rows),
            "max_ai_prob": round(max(ai_vals), 6) if ai_vals else 0.0,
            "avg_ai_prob": round(mean(ai_vals), 6) if ai_vals else 0.0,
            "max_setup_quality": round(max(q_vals), 6) if q_vals else 0.0,
            "avg_setup_quality": round(mean(q_vals), 6) if q_vals else 0.0,
            "max_abs_technical_score": round(max(tech_vals), 6) if tech_vals else 0.0,
            "top_quasi_signals": _top_rows(near_rows, limit=8),
        }

    near_candidates = [r for r in diagnostics if _bool(r.get("near_candidate"))]
    exploratory_candidates = [r for r in diagnostics if _bool(r.get("exploratory_candidate"))]
    accepted = [r for r in diagnostics if str(r.get("dominant_filter") or "") == "ACCEPTED"]
    thresholds = thresholds_from_config()
    conclusions: list[str] = []
    if diagnostics and not accepted:
        conclusions.append("No accepted paper signals were observed in the diagnostic sample.")
    if filter_counts.get("META_PROB_LOW", 0) >= max(1, len(diagnostics) * 0.1):
        conclusions.append("META_PROB_LOW is a material blocker; probability calibration should be reviewed before changing gates.")
    if event_counts.get("SIGNAL_DETECTED", 0) == 0 and exploratory_candidates:
        conclusions.append("Exploratory candidates exist, but they are diagnostic-only and do not change live/paper decisions.")
    if event_counts.get("SIGNAL_DETECTED", 0) == 0 and not exploratory_candidates:
        conclusions.append("Even exploratory thresholds found no unlock candidates; keep current gates and collect more data.")

    return {
        "generated_at": utc_now_iso(),
        "status": "WARN" if event_counts.get("SIGNAL_DETECTED", 0) == 0 and diagnostics else "PASS",
        "diagnostic_only": True,
        "strategy_changed": False,
        "runtime_files": {
            "events": str(events_path),
            "report": str(data_path / "paper_signal_diagnostics_report.json"),
        },
        "thresholds": {
            "meta_prob_threshold": thresholds.meta_prob_threshold,
            "meta_quality_threshold": thresholds.meta_quality_threshold,
            "trending_threshold": thresholds.trending_threshold,
            "ranging_threshold": thresholds.ranging_threshold,
            "exploratory_enabled": thresholds.exploratory_enabled,
            "exploratory_meta_prob_threshold": thresholds.exploratory_meta_prob_threshold,
            "exploratory_ranging_meta_prob_threshold": thresholds.exploratory_ranging_meta_prob_threshold,
            "exploratory_min_setup_quality": thresholds.exploratory_min_setup_quality,
        },
        "counts": {
            "events_total": len(events),
            "asset_scanned": event_counts.get("ASSET_SCANNED", 0),
            "diagnostics": len(diagnostics),
            "no_signal": event_counts.get("NO_SIGNAL", 0),
            "signals_detected": event_counts.get("SIGNAL_DETECTED", 0),
            "orders_submitted": event_counts.get("PAPER_ORDER_SUBMITTED", 0),
            "positions_opened": event_counts.get("POSITION_OPENED", 0),
            "near_candidates": len(near_candidates),
            "exploratory_candidates": len(exploratory_candidates),
        },
        "dominant_filters": dict(filter_counts.most_common()),
        "by_asset": by_asset,
        "top_quasi_signals": _top_rows(near_candidates, limit=top_n),
        "top_exploratory_unlock_candidates": _top_rows(exploratory_candidates, limit=top_n),
        "conclusions": conclusions,
    }


def write_signal_diagnostics_report(data_dir: str | Path) -> dict[str, Any]:
    path = Path(data_dir) / "paper_signal_diagnostics_report.json"
    report = build_signal_diagnostics_report(data_dir)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


# ---------------------------------------------------------------------------
# Prompt 29.4.2a — Historical signal diagnostics backfill
# ---------------------------------------------------------------------------
# Backfill is deliberately inference-only for legacy NO_SIGNAL events that were
# written before SIGNAL_DIAGNOSTIC existed.  It never modifies decisions, risk,
# orders, positions, or broker state.

BACKFILL_REPORT_NAME = "paper_signal_diagnostics_backfill_report.json"


def _event_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("cycle_id") or ""),
        str(event.get("symbol") or "UNKNOWN"),
        str(event.get("candle_ts") or ""),
    )


def _legacy_confidence(event: dict[str, Any]) -> dict[str, Any]:
    conf = event.get("confidence")
    return conf if isinstance(conf, dict) else {}


def _infer_regime(event: dict[str, Any]) -> tuple[str, str]:
    conf = _legacy_confidence(event)
    raw = event.get("regime") or event.get("market_regime") or conf.get("regime") or conf.get("market_regime")
    if raw:
        return str(raw).upper(), "event"
    return "RANGING", "inferred_default_ranging"


def infer_legacy_no_signal_diagnostic(event: dict[str, Any]) -> dict[str, Any]:
    """Infer a diagnostic row from a legacy NO_SIGNAL event.

    This function intentionally uses only values persisted in paper_events.jsonl.
    Therefore it is less precise than a real SIGNAL_DIAGNOSTIC event.  The output
    is explicitly marked inference_method=legacy_no_signal_heuristic.
    """
    conf = _legacy_confidence(event)
    thresholds = thresholds_from_config()
    regime, regime_source = _infer_regime(event)
    active_threshold = thresholds.trending_threshold if regime == "TRENDING" else thresholds.ranging_threshold

    tech_score = safe_float(conf.get("tech_score"), safe_float(event.get("score"), 0.0))
    ai_prob = safe_float(conf.get("ai_prob"), 0.0)
    setup_quality = safe_float(conf.get("setup_quality"), 0.0)
    abs_score = abs(tech_score)
    event_filter = str(event.get("diagnostic_filter") or "").upper()
    event_reason = str(event.get("diagnostic_reason") or "")

    if event_filter:
        dominant_filter = event_filter
        reason = event_reason or "diagnostic_filter already present on NO_SIGNAL event"
        confidence_level = "medium"
    elif abs_score < active_threshold:
        dominant_filter = "TECH_SCORE_LOW"
        reason = f"inferred: abs_tech_score {abs_score:.2f} below {active_threshold:.2f} {regime} threshold"
        confidence_level = "high"
    elif setup_quality > 0:
        if ai_prob < thresholds.meta_prob_threshold:
            dominant_filter = "META_PROB_LOW"
            reason = f"inferred: ai_prob {ai_prob:.2f} below {thresholds.meta_prob_threshold:.2f}"
            confidence_level = "high"
        elif setup_quality < thresholds.meta_quality_threshold:
            dominant_filter = "SETUP_QUALITY_LOW"
            reason = f"inferred: setup_quality {setup_quality:.2f} below {thresholds.meta_quality_threshold:.2f}"
            confidence_level = "high"
        else:
            dominant_filter = "POST_META_FILTERED"
            reason = "inferred: technical/meta values looked acceptable but final verdict stayed HOLD"
            confidence_level = "low"
    elif ai_prob >= thresholds.meta_prob_threshold and setup_quality <= 0:
        dominant_filter = "SETUP_QUALITY_LOW"
        reason = "inferred: neutral/high ai_prob but setup_quality absent/zero"
        confidence_level = "medium"
    else:
        dominant_filter = "NO_TECHNICAL_CANDIDATE"
        reason = "inferred: no persisted evidence of a technical/meta candidate"
        confidence_level = "medium"

    intended_side = "BUY" if tech_score >= active_threshold else "SELL" if tech_score <= -active_threshold else "HOLD"
    exploratory_prob_threshold = thresholds.exploratory_ranging_meta_prob_threshold if regime == "RANGING" else thresholds.exploratory_meta_prob_threshold
    near_candidate = bool(abs_score >= max(0.0, active_threshold - 5.0) or setup_quality >= thresholds.meta_quality_threshold)
    exploratory_candidate = bool(
        thresholds.exploratory_enabled
        and intended_side in {"BUY", "SELL"}
        and ai_prob >= exploratory_prob_threshold
        and setup_quality >= thresholds.exploratory_min_setup_quality
        and dominant_filter in {"META_PROB_LOW", "POST_META_FILTERED", "META_FILTERED", "POST_TECH_FILTERED"}
    )

    return {
        "event_type": "SIGNAL_DIAGNOSTIC_BACKFILL",
        "source_event_type": str(event.get("event_type") or "NO_SIGNAL"),
        "cycle_id": event.get("cycle_id"),
        "cycle_seq": cycle_seq(event.get("cycle_id")),
        "symbol": event.get("symbol") or "UNKNOWN",
        "candle_ts": event.get("candle_ts"),
        "ts": event.get("ts"),
        "backfilled_at": utc_now_iso(),
        "inference_method": "legacy_no_signal_heuristic",
        "inferred": True,
        "exact": False,
        "confidence_level": confidence_level,
        "regime": regime,
        "regime_source": regime_source,
        "dominant_filter": dominant_filter,
        "diagnostic_reason": reason,
        "technical_score": round(tech_score, 6),
        "abs_technical_score": round(abs_score, 6),
        "ai_prob": round(ai_prob, 8),
        "setup_quality": round(setup_quality, 8),
        "final_verdict": str(event.get("verdict") or "HOLD").upper(),
        "final_score": safe_int(event.get("score"), 0),
        "intended_side": intended_side,
        "near_candidate": near_candidate,
        "exploratory_candidate": exploratory_candidate,
        "regular_gate_missing": {
            "tech_score_gap": round(max(0.0, active_threshold - abs_score), 6),
            "meta_prob_gap": round(max(0.0, thresholds.meta_prob_threshold - ai_prob), 6),
            "setup_quality_gap": round(max(0.0, thresholds.meta_quality_threshold - setup_quality), 6),
        },
        "thresholds": {
            "active_score_threshold": active_threshold,
            "meta_prob_threshold": thresholds.meta_prob_threshold,
            "meta_quality_threshold": thresholds.meta_quality_threshold,
            "exploratory_meta_prob_threshold": exploratory_prob_threshold,
            "exploratory_min_setup_quality": thresholds.exploratory_min_setup_quality,
        },
        "technical_confidence": {
            k: conf.get(k)
            for k in ["bias", "ema", "engulfing", "psy_level", "rsi", "support"]
            if k in conf
        },
        "diagnostic_only": True,
        "strategy_changed": False,
    }


def _bucket(value: float, edges: list[float]) -> str:
    if not math.isfinite(value):
        return "NA"
    prev = None
    for edge in edges:
        if value < edge:
            return f"<{edge:g}" if prev is None else f"{prev:g}-{edge:g}"
        prev = edge
    return f">={edges[-1]:g}" if edges else "NA"


def _distribution(rows: list[dict[str, Any]], field: str, edges: list[float]) -> dict[str, int]:
    c = Counter(_bucket(safe_float(r.get(field), 0.0), edges) for r in rows)
    return dict(c.most_common())


def _summarize_rows(rows: list[dict[str, Any]], *, limit: int = 25) -> dict[str, Any]:
    filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in rows)
    near = [r for r in rows if _bool(r.get("near_candidate"))]
    exploratory = [r for r in rows if _bool(r.get("exploratory_candidate"))]
    meta = [r for r in rows if safe_float(r.get("setup_quality"), 0.0) > 0]
    ai_vals = [safe_float(r.get("ai_prob"), 0.0) for r in meta]
    q_vals = [safe_float(r.get("setup_quality"), 0.0) for r in meta]
    t_vals = [abs(safe_float(r.get("technical_score"), 0.0)) for r in rows]
    return {
        "rows": len(rows),
        "dominant_filters": dict(filters.most_common()),
        "near_candidates": len(near),
        "exploratory_candidates": len(exploratory),
        "meta_reached": len(meta),
        "max_ai_prob": round(max(ai_vals), 6) if ai_vals else 0.0,
        "avg_ai_prob": round(mean(ai_vals), 6) if ai_vals else 0.0,
        "max_setup_quality": round(max(q_vals), 6) if q_vals else 0.0,
        "avg_setup_quality": round(mean(q_vals), 6) if q_vals else 0.0,
        "max_abs_technical_score": round(max(t_vals), 6) if t_vals else 0.0,
        "ai_prob_distribution": _distribution(rows, "ai_prob", [30, 35, 40, 45, 50, 55, 60, 70]),
        "setup_quality_distribution": _distribution(rows, "setup_quality", [1, 25, 50, 60, 70, 80, 90]),
        "technical_score_distribution": _distribution(rows, "abs_technical_score", [10, 20, 25, 30, 40, 50, 60]),
        "top_quasi_signals": _top_rows(near, limit=limit),
        "top_exploratory_unlock_candidates": _top_rows(exploratory, limit=limit),
    }


def build_signal_diagnostics_backfill_report(data_dir: str | Path, *, top_n: int = 25) -> dict[str, Any]:
    data_path = Path(data_dir)
    events_path = data_path / "paper_events.jsonl"
    events = read_jsonl(events_path)
    event_counts = Counter(str(e.get("event_type") or "").upper() for e in events)
    exact = [e for e in events if str(e.get("event_type") or "").upper() == DIAGNOSTIC_EVENT_TYPE]
    exact_keys = {_event_key(e) for e in exact}

    legacy_no_signal = [e for e in events if str(e.get("event_type") or "").upper() == "NO_SIGNAL"]
    inferred: list[dict[str, Any]] = []
    skipped_exact_overlap = 0
    for e in legacy_no_signal:
        if _event_key(e) in exact_keys:
            skipped_exact_overlap += 1
            continue
        inferred.append(infer_legacy_no_signal_diagnostic(e))

    combined: list[dict[str, Any]] = []
    for e in exact:
        row = dict(e)
        row["exact"] = True
        row["inferred"] = False
        row.setdefault("abs_technical_score", abs(safe_float(row.get("technical_score"), 0.0)))
        row.setdefault("cycle_seq", cycle_seq(row.get("cycle_id")))
        combined.append(row)
    combined.extend(inferred)

    by_asset: dict[str, Any] = {}
    raw_by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in combined:
        raw_by_asset[str(row.get("symbol") or "UNKNOWN")].append(row)
    for symbol, rows in sorted(raw_by_asset.items()):
        exact_rows = [r for r in rows if r.get("exact") is True]
        inferred_rows = [r for r in rows if r.get("inferred") is True]
        by_asset[symbol] = {
            "combined": _summarize_rows(rows, limit=8),
            "exact_rows": len(exact_rows),
            "inferred_rows": len(inferred_rows),
            "inferred_confidence_levels": dict(Counter(str(r.get("confidence_level") or "exact") for r in inferred_rows).most_common()),
        }

    thresholds = thresholds_from_config()
    combined_filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in combined)
    inferred_filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in inferred)
    exact_filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in exact)
    near = [r for r in combined if _bool(r.get("near_candidate"))]
    exploratory = [r for r in combined if _bool(r.get("exploratory_candidate"))]
    meta_low = combined_filters.get("META_PROB_LOW", 0)
    tech_low = combined_filters.get("TECH_SCORE_LOW", 0)

    conclusions: list[str] = []
    if event_counts.get("SIGNAL_DETECTED", 0) == 0:
        conclusions.append("No accepted paper signals are present in the historical event log.")
    if inferred:
        conclusions.append("Legacy NO_SIGNAL events were backfilled with heuristic diagnostics; treat them as inferred, not exact.")
    if meta_low:
        conclusions.append("META_PROB_LOW appears in historical diagnostics; probability calibration remains a candidate blocker.")
    if tech_low >= max(1, len(combined) * 0.5):
        conclusions.append("TECH_SCORE_LOW dominates many scans; broad threshold relaxation would change strategy behavior and is not recommended without backtest validation.")
    if exploratory:
        conclusions.append("Exploratory unlock candidates exist for analysis only; PAPER_ENTRY_UNLOCK_ENABLED remains false.")
    else:
        conclusions.append("No exploratory unlock candidates found under current conservative exploratory thresholds.")

    coverage_pct = pct(len(inferred) + len(exact), event_counts.get("NO_SIGNAL", 0) + len(exact))
    return {
        "generated_at": utc_now_iso(),
        "status": "WARN" if event_counts.get("SIGNAL_DETECTED", 0) == 0 else "PASS",
        "diagnostic_only": True,
        "strategy_changed": False,
        "backfill_inference": True,
        "runtime_files": {
            "events": str(events_path),
            "exact_report": str(data_path / "paper_signal_diagnostics_report.json"),
            "backfill_report": str(data_path / BACKFILL_REPORT_NAME),
        },
        "thresholds": {
            "meta_prob_threshold": thresholds.meta_prob_threshold,
            "meta_quality_threshold": thresholds.meta_quality_threshold,
            "trending_threshold": thresholds.trending_threshold,
            "ranging_threshold": thresholds.ranging_threshold,
            "exploratory_enabled": thresholds.exploratory_enabled,
            "exploratory_meta_prob_threshold": thresholds.exploratory_meta_prob_threshold,
            "exploratory_ranging_meta_prob_threshold": thresholds.exploratory_ranging_meta_prob_threshold,
            "exploratory_min_setup_quality": thresholds.exploratory_min_setup_quality,
        },
        "counts": {
            "events_total": len(events),
            "asset_scanned": event_counts.get("ASSET_SCANNED", 0),
            "no_signal_events": event_counts.get("NO_SIGNAL", 0),
            "exact_diagnostics": len(exact),
            "inferred_diagnostics": len(inferred),
            "combined_diagnostics": len(combined),
            "skipped_no_signal_with_exact_diagnostic": skipped_exact_overlap,
            "coverage_pct": round(coverage_pct, 4),
            "signals_detected": event_counts.get("SIGNAL_DETECTED", 0),
            "orders_submitted": event_counts.get("PAPER_ORDER_SUBMITTED", 0),
            "positions_opened": event_counts.get("POSITION_OPENED", 0),
            "near_candidates": len(near),
            "exploratory_candidates": len(exploratory),
        },
        "dominant_filters": {
            "combined": dict(combined_filters.most_common()),
            "exact": dict(exact_filters.most_common()),
            "inferred": dict(inferred_filters.most_common()),
        },
        "distributions": {
            "combined_ai_prob": _distribution(combined, "ai_prob", [30, 35, 40, 45, 50, 55, 60, 70]),
            "combined_setup_quality": _distribution(combined, "setup_quality", [1, 25, 50, 60, 70, 80, 90]),
            "combined_abs_technical_score": _distribution(combined, "abs_technical_score", [10, 20, 25, 30, 40, 50, 60]),
        },
        "by_asset": by_asset,
        "top_quasi_signals": _top_rows(near, limit=top_n),
        "top_exploratory_unlock_candidates": _top_rows(exploratory, limit=top_n),
        "conclusions": conclusions,
    }


def write_signal_diagnostics_backfill_report(data_dir: str | Path) -> dict[str, Any]:
    path = Path(data_dir) / BACKFILL_REPORT_NAME
    report = build_signal_diagnostics_backfill_report(data_dir)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
