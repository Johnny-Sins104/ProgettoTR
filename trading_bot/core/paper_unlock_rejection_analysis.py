"""Prompt 29.4.4a unlock rejection analysis utilities.

Diagnostic-only report for the paper-only unlock gate.  It reads paper runtime
JSONL events and explains why Prompt 29.4.4 evaluates unlock candidates without
necessarily producing PAPER_UNLOCK_SIGNAL events.

Safety rules:
- read-only with respect to broker/order state;
- no strategy threshold changes;
- no paper orders, no testnet, no live execution;
- output is an audit report under data/paper_unlock_rejection_report.json.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import json
import re

from core.paper_lifecycle import read_events


RANGE_POS_RE = re.compile(r"range_pos_400\s+([0-9]*\.?[0-9]+)\s*([<>]=?)\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class UnlockRejectionPaths:
    data_dir: Path

    @property
    def events_path(self) -> Path:
        return self.data_dir / "paper_events.jsonl"

    @property
    def report_path(self) -> Path:
        return self.data_dir / "paper_unlock_rejection_report.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "").upper()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _safe_mean(values: list[float]) -> float:
    return round(mean(values), 8) if values else 0.0


def _pct(n: int | float, d: int | float) -> float:
    try:
        d = float(d)
        if d == 0:
            return 0.0
        return float(n) / d * 100.0
    except Exception:
        return 0.0


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}
    ordered = sorted(values)

    def pick(q: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        idx = int(round((len(ordered) - 1) * q))
        idx = max(0, min(len(ordered) - 1, idx))
        return ordered[idx]

    return {
        "min": round(ordered[0], 8),
        "p25": round(pick(0.25), 8),
        "median": round(pick(0.50), 8),
        "p75": round(pick(0.75), 8),
        "max": round(ordered[-1], 8),
        "avg": _safe_mean(ordered),
    }


def _counter_dict(counter: Counter[Any], limit: int | None = None) -> dict[str, int]:
    rows = counter.most_common(limit) if limit else counter.most_common()
    return {str(k): int(v) for k, v in rows}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (str(event.get("cycle_id") or ""), str(event.get("symbol") or ""), str(event.get("candle_ts") or ""))


def _normalize_rejection_reason(reason: str) -> str:
    raw = str(reason or "").strip()
    if not raw:
        return "unknown"
    if raw.startswith("filter_not_allowed:"):
        filt = raw.split(":", 1)[1] or "-"
        return f"filter_not_allowed:{filt}"
    return raw


def _parse_range_position(text: str) -> dict[str, Any]:
    match = RANGE_POS_RE.search(str(text or ""))
    if not match:
        return {}
    return {
        "range_pos_400": round(_safe_float(match.group(1)), 8),
        "operator": match.group(2),
        "threshold": round(_safe_float(match.group(3)), 8),
    }


def _extract_thresholds(decision: dict[str, Any], fallback: dict[str, Any]) -> dict[str, float]:
    missing = _as_dict(decision.get("missing"))
    thresholds = _as_dict(decision.get("thresholds"))
    fb_thresholds = _as_dict(fallback.get("thresholds"))
    return {
        "active_score_threshold": _safe_float(decision.get("active_score_threshold"), _safe_float(fb_thresholds.get("active_score_threshold"), _safe_float(thresholds.get("active_score_threshold"), 0.0))),
        "ai_prob_gap": _safe_float(missing.get("ai_prob_gap"), 0.0),
        "setup_quality_gap": _safe_float(missing.get("setup_quality_gap"), 0.0),
        "tech_score_gap": _safe_float(missing.get("tech_score_gap"), 0.0),
    }


def _merged_eval_row(event: dict[str, Any], no_signal: dict[str, Any] | None) -> dict[str, Any]:
    no_signal = no_signal or {}
    decision = _as_dict(event.get("decision"))
    confidence = _as_dict(no_signal.get("confidence"))
    thresholds = _extract_thresholds(decision, no_signal)

    ai_prob = _safe_float(decision.get("ai_prob"), 0.0)
    if ai_prob <= 0.0:
        ai_prob = _safe_float(confidence.get("ai_prob"), 0.0)
    setup_quality = _safe_float(decision.get("setup_quality"), 0.0)
    if setup_quality <= 0.0:
        setup_quality = _safe_float(confidence.get("setup_quality"), 0.0)
    technical_score = _safe_float(decision.get("technical_score"), 0.0)
    if technical_score == 0.0:
        technical_score = _safe_float(confidence.get("tech_score"), _safe_float(no_signal.get("score"), 0.0))

    dominant_filter = str(decision.get("dominant_filter") or no_signal.get("diagnostic_filter") or "")
    reason = _normalize_rejection_reason(str(event.get("reason") or decision.get("reason") or no_signal.get("paper_unlock_reason") or ""))
    diagnostic_reason = str(no_signal.get("diagnostic_reason") or "")
    range_data = _parse_range_position(diagnostic_reason)

    side = str(decision.get("side") or "").upper()
    if side not in {"BUY", "SELL"}:
        if technical_score > 0:
            side = "INFERRED_BUY"
        elif technical_score < 0:
            side = "INFERRED_SELL"
        else:
            side = ""

    return {
        "line_no": event.get("__line_no__"),
        "ts": event.get("ts"),
        "cycle_id": event.get("cycle_id"),
        "candle_ts": event.get("candle_ts"),
        "symbol": str(event.get("symbol") or decision.get("symbol") or ""),
        "accepted": bool(event.get("accepted") or decision.get("accepted")),
        "reason": reason,
        "side": side,
        "profile": str(decision.get("profile") or ""),
        "tag": str(decision.get("tag") or ""),
        "dominant_filter": dominant_filter,
        "diagnostic_filter": str(no_signal.get("diagnostic_filter") or ""),
        "diagnostic_reason": diagnostic_reason,
        "ai_prob": round(ai_prob, 8),
        "setup_quality": round(setup_quality, 8),
        "technical_score": round(technical_score, 8),
        "abs_technical_score": round(abs(technical_score), 8),
        "active_score_threshold": round(thresholds["active_score_threshold"], 8),
        "ai_prob_gap": round(thresholds["ai_prob_gap"], 8),
        "setup_quality_gap": round(thresholds["setup_quality_gap"], 8),
        "tech_score_gap": round(thresholds["tech_score_gap"], 8),
        "range_position": range_data,
        "exploratory_candidate": bool(no_signal.get("exploratory_candidate")),
    }


def _is_near_threshold(row: dict[str, Any]) -> bool:
    if row.get("accepted"):
        return False
    # Near-candidate definition is deliberately diagnostic-only.  It flags rows
    # that failed by small margins, not rows to trade.
    ai_gap = _safe_float(row.get("ai_prob_gap"), 999.0)
    quality_gap = _safe_float(row.get("setup_quality_gap"), 999.0)
    tech_gap = _safe_float(row.get("tech_score_gap"), 999.0)
    ai = _safe_float(row.get("ai_prob"), 0.0)
    quality = _safe_float(row.get("setup_quality"), 0.0)
    return (ai >= 35.0 and quality >= 50.0 and ai_gap <= 5.0 and quality_gap <= 10.0 and tech_gap <= 10.0)


def _recommendation(rows: list[dict[str, Any]], reason_counts: Counter[str], btc_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NO_UNLOCK_EVALUATIONS",
            "action": "verify_29_4_4_runtime_or_enable_paper_unlock_before_tuning",
            "next_patch": "29.4.4a rerun after PAPER_UNLOCK_EVALUATED events exist",
        }
    accepted = [r for r in rows if r.get("accepted")]
    if accepted:
        return {
            "status": "UNLOCK_SIGNALS_PRESENT",
            "action": "do_not_relax_gates; audit opened paper trades first",
            "next_patch": "29.4.8 Paper trade quality audit",
            "accepted_rows": len(accepted),
        }
    dominant, count = reason_counts.most_common(1)[0] if reason_counts else ("unknown", 0)
    btc_reason_counts = Counter(str(r.get("reason") or "unknown") for r in btc_rows)
    btc_dominant, btc_count = btc_reason_counts.most_common(1)[0] if btc_reason_counts else (dominant, count)
    near = [r for r in btc_rows if _is_near_threshold(r)]

    if btc_dominant == "no_intended_side":
        return {
            "status": "NO_DIRECTION_DOMINANT",
            "action": "do_not_relax_thresholds; improve scenario/side attribution before paper expansion",
            "next_patch": "29.5.0a Crypto intraday scenario engine",
            "dominant_btc_reason": btc_dominant,
            "dominant_btc_count": btc_count,
            "near_threshold_btc_rows": len(near),
        }
    if btc_dominant.startswith("filter_not_allowed:RANGE_POSITION_FILTERED"):
        return {
            "status": "RANGE_FILTER_DOMINANT",
            "action": "keep RANGE_POSITION_FILTERED blocked operationally; run shadow-only range-position experiment",
            "next_patch": "29.4.4b Controlled range-position shadow experiment",
            "dominant_btc_reason": btc_dominant,
            "dominant_btc_count": btc_count,
            "near_threshold_btc_rows": len(near),
        }
    if btc_dominant in {"technical_gate_not_met", "TECH_SCORE_LOW"} or "TECH_SCORE_LOW" in btc_reason_counts:
        return {
            "status": "TECHNICAL_SCORE_WEAK",
            "action": "do_not unlock; improve market-structure/scenario scoring before relaxing gates",
            "next_patch": "29.5.0a Crypto intraday scenario engine",
            "dominant_btc_reason": btc_dominant,
            "dominant_btc_count": btc_count,
            "near_threshold_btc_rows": len(near),
        }
    if near:
        return {
            "status": "NEAR_THRESHOLD_ROWS_FOUND",
            "action": "compare profile variants in shadow; do not change operational profile automatically",
            "next_patch": "29.4.4c Paper unlock profile refinement",
            "dominant_btc_reason": btc_dominant,
            "dominant_btc_count": btc_count,
            "near_threshold_btc_rows": len(near),
        }
    return {
        "status": "STRICT_GATE_NO_ACCEPTED_ROWS",
        "action": "continue collecting data or run profile refinement only in shadow",
        "next_patch": "29.4.4c Paper unlock profile refinement",
        "dominant_btc_reason": btc_dominant,
        "dominant_btc_count": btc_count,
        "near_threshold_btc_rows": len(near),
    }


def build_unlock_rejection_report(data_dir: str | Path) -> dict[str, Any]:
    paths = UnlockRejectionPaths(Path(data_dir))
    events = read_events(paths.events_path)
    event_counts = Counter(_event_type(e) for e in events)

    no_signal_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        if _event_type(event) == "NO_SIGNAL":
            no_signal_by_key[_key(event)] = event

    rows: list[dict[str, Any]] = []
    for event in events:
        if _event_type(event) != "PAPER_UNLOCK_EVALUATED":
            continue
        rows.append(_merged_eval_row(event, no_signal_by_key.get(_key(event))))

    reason_counts = Counter(str(r.get("reason") or "unknown") for r in rows)
    asset_counts = Counter(str(r.get("symbol") or "unknown") for r in rows)
    accepted_rows = [r for r in rows if r.get("accepted")]
    rejected_rows = [r for r in rows if not r.get("accepted")]
    btc_rows = [r for r in rows if r.get("symbol") == "BTC/USDT"]
    btc_rejected = [r for r in btc_rows if not r.get("accepted")]
    near_rows = [r for r in rows if _is_near_threshold(r)]
    btc_near_rows = [r for r in btc_rows if _is_near_threshold(r)]

    by_asset: dict[str, Any] = {}
    for symbol in sorted(set(asset_counts.keys())):
        symbol_rows = [r for r in rows if r.get("symbol") == symbol]
        accepted = [r for r in symbol_rows if r.get("accepted")]
        rejected = [r for r in symbol_rows if not r.get("accepted")]
        by_asset[symbol] = {
            "evaluated": len(symbol_rows),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "accepted_rate_pct": round(_pct(len(accepted), len(symbol_rows)), 4),
            "reasons": _counter_dict(Counter(str(r.get("reason") or "unknown") for r in symbol_rows)),
            "dominant_filters": _counter_dict(Counter(str(r.get("dominant_filter") or r.get("diagnostic_filter") or "unknown") for r in symbol_rows)),
            "sides": _counter_dict(Counter(str(r.get("side") or "unknown") for r in symbol_rows)),
            "near_threshold_candidates": sum(1 for r in symbol_rows if _is_near_threshold(r)),
            "metrics": {
                "ai_prob": _quantiles([_safe_float(r.get("ai_prob"), 0.0) for r in symbol_rows]),
                "setup_quality": _quantiles([_safe_float(r.get("setup_quality"), 0.0) for r in symbol_rows]),
                "abs_technical_score": _quantiles([_safe_float(r.get("abs_technical_score"), 0.0) for r in symbol_rows]),
                "tech_score_gap": _quantiles([_safe_float(r.get("tech_score_gap"), 0.0) for r in symbol_rows]),
            },
            "recent_rejections": [
                {
                    "ts": r.get("ts"),
                    "cycle_id": r.get("cycle_id"),
                    "candle_ts": r.get("candle_ts"),
                    "reason": r.get("reason"),
                    "dominant_filter": r.get("dominant_filter"),
                    "ai_prob": r.get("ai_prob"),
                    "setup_quality": r.get("setup_quality"),
                    "technical_score": r.get("technical_score"),
                    "diagnostic_reason": r.get("diagnostic_reason"),
                }
                for r in rejected[-5:]
            ],
        }

    range_rows = [r for r in rows if str(r.get("reason") or "").startswith("filter_not_allowed:RANGE_POSITION_FILTERED") or str(r.get("dominant_filter") or r.get("diagnostic_filter") or "") == "RANGE_POSITION_FILTERED"]
    range_positions = [_safe_float(_as_dict(r.get("range_position")).get("range_pos_400"), -1.0) for r in range_rows]
    range_positions = [x for x in range_positions if x >= 0.0]
    range_review = {
        "evaluated": len(range_rows),
        "btc_only": sum(1 for r in range_rows if r.get("symbol") == "BTC/USDT"),
        "sides": _counter_dict(Counter(str(r.get("side") or "unknown") for r in range_rows)),
        "range_pos_400": _quantiles(range_positions),
        "near_threshold_candidates": sum(1 for r in range_rows if _is_near_threshold(r)),
        "examples": [
            {
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "cycle_id": r.get("cycle_id"),
                "candle_ts": r.get("candle_ts"),
                "range_position": r.get("range_position"),
                "technical_score": r.get("technical_score"),
                "ai_prob": r.get("ai_prob"),
                "setup_quality": r.get("setup_quality"),
                "diagnostic_reason": r.get("diagnostic_reason"),
            }
            for r in range_rows[-10:]
        ],
        "recommendation": "KEEP_BLOCKED" if not range_rows or not any(_is_near_threshold(r) for r in range_rows) else "REVIEW_ONLY",
        "safety_note": "Range-filtered rows remain operationally blocked. This section is diagnostic-only.",
    }

    recommendation = _recommendation(rows, reason_counts, btc_rows)
    warnings: list[str] = []
    if rows and not accepted_rows:
        warnings.append("unlock_evaluated_but_no_accepted_signals")
    if btc_rows and not any(r.get("accepted") for r in btc_rows):
        warnings.append("btc_unlock_zero_acceptance")
    if event_counts.get("PAPER_UNLOCK_SIGNAL", 0) != len(accepted_rows):
        warnings.append("unlock_signal_event_count_differs_from_accepted_evaluations")

    return {
        "generated_at": utc_now_iso(),
        "status": "WARN" if warnings else "PASS",
        "prompt": "29.4.4a",
        "report_type": "unlock_rejection_analysis",
        "safety": {
            "diagnostic_only": True,
            "opens_orders": False,
            "changes_thresholds": False,
            "enables_live_or_testnet": False,
            "range_position_operational_unlock": False,
        },
        "files": {
            "events": str(paths.events_path),
            "report": str(paths.report_path),
        },
        "counts": {
            "events_total": len(events),
            "paper_unlock_evaluated": len(rows),
            "paper_unlock_accepted_evaluations": len(accepted_rows),
            "paper_unlock_rejected_evaluations": len(rejected_rows),
            "paper_unlock_signal_events": int(event_counts.get("PAPER_UNLOCK_SIGNAL", 0)),
            "paper_order_submitted_events": int(event_counts.get("PAPER_ORDER_SUBMITTED", 0)),
            "position_opened_events": int(event_counts.get("POSITION_OPENED", 0)),
            "btc_evaluated": len(btc_rows),
            "btc_rejected": len(btc_rejected),
            "near_threshold_candidates": len(near_rows),
            "btc_near_threshold_candidates": len(btc_near_rows),
        },
        "rejection_reasons": _counter_dict(reason_counts),
        "assets": _counter_dict(asset_counts),
        "by_asset": by_asset,
        "btc_focus": by_asset.get("BTC/USDT", {}),
        "range_position_review": range_review,
        "near_threshold_examples": [
            {
                "symbol": r.get("symbol"),
                "cycle_id": r.get("cycle_id"),
                "candle_ts": r.get("candle_ts"),
                "reason": r.get("reason"),
                "dominant_filter": r.get("dominant_filter"),
                "side": r.get("side"),
                "ai_prob": r.get("ai_prob"),
                "setup_quality": r.get("setup_quality"),
                "technical_score": r.get("technical_score"),
                "missing": {
                    "ai_prob_gap": r.get("ai_prob_gap"),
                    "setup_quality_gap": r.get("setup_quality_gap"),
                    "tech_score_gap": r.get("tech_score_gap"),
                },
            }
            for r in btc_near_rows[-20:]
        ],
        "decision": recommendation,
        "warnings": warnings,
    }


def write_unlock_rejection_report(data_dir: str | Path) -> dict[str, Any]:
    paths = UnlockRejectionPaths(Path(data_dir))
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    report = build_unlock_rejection_report(paths.data_dir)
    paths.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build ProgettoTR paper unlock rejection report.")
    parser.add_argument("--data-dir", default="data")
    ns = parser.parse_args()
    out = write_unlock_rejection_report(ns.data_dir)
    print(json.dumps({"status": out.get("status"), "counts": out.get("counts"), "decision": out.get("decision")}, indent=2, sort_keys=True))
