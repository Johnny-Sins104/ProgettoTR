from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _iter_jsonl_tail(path: Path, max_lines: int) -> list[dict[str, Any]]:
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, max_lines))
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return list(rows)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "")


def _quantiles(values: Iterable[float]) -> dict[str, Any]:
    rows = sorted(v for v in values if v == v and v not in {float("inf"), float("-inf")})
    if not rows:
        return {"count": 0, "min": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(pct: float) -> float:
        if len(rows) == 1:
            return rows[0]
        return rows[int(round((len(rows) - 1) * pct))]

    return {
        "count": len(rows),
        "min": round(rows[0], 6),
        "median": round(pick(0.50), 6),
        "p75": round(pick(0.75), 6),
        "max": round(rows[-1], 6),
        "avg": round(sum(rows) / len(rows), 6),
    }


def _top(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _side(event: dict[str, Any]) -> str:
    for key in ("technical_verdict", "intended_side", "side"):
        value = str(event.get(key) or "").upper()
        if value in {"BUY", "SELL"}:
            return value
    score = _safe_float(event.get("technical_score") if "technical_score" in event else event.get("score"))
    if score > 0:
        return "BUY"
    if score < 0:
        return "SELL"
    return "HOLD"


def _active_threshold(event: dict[str, Any]) -> float:
    thresholds = event.get("thresholds")
    if isinstance(thresholds, dict):
        value = _safe_float(thresholds.get("active_score_threshold"))
        if value > 0:
            return value
    regime = str(event.get("regime") or "").upper()
    return 60.0 if regime == "TRENDING" else 30.0


def _signal_snapshot(event: dict[str, Any], no_signal_by_cycle: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cycle_id = str(event.get("cycle_id") or "")
    no_signal = no_signal_by_cycle.get(cycle_id, {})
    return {
        "cycle_id": cycle_id,
        "symbol": event.get("symbol"),
        "side": _side(event),
        "ai_prob": _safe_float(event.get("ai_prob")),
        "setup_quality": _safe_float(event.get("setup_quality")),
        "technical_score": _safe_float(event.get("technical_score") if "technical_score" in event else event.get("score")),
        "active_threshold": _active_threshold(event),
        "filter": event.get("dominant_filter") or event.get("diagnostic_filter") or no_signal.get("diagnostic_filter"),
        "reason": event.get("diagnostic_reason") or no_signal.get("diagnostic_reason"),
        "scenario": no_signal.get("scenario") or "-",
        "scenario_bias": no_signal.get("scenario_directional_bias") or "-",
        "scenario_recommendation": no_signal.get("scenario_recommendation") or "-",
        "candle_ts": event.get("candle_ts") or no_signal.get("candle_ts"),
        "ts": event.get("ts") or no_signal.get("ts"),
    }


def _passes_profile(snapshot: dict[str, Any], profile: dict[str, Any]) -> bool:
    side = str(snapshot.get("side") or "").upper()
    abs_score = abs(_safe_float(snapshot.get("technical_score")))
    active_threshold = _safe_float(snapshot.get("active_threshold"))
    near_gap = _safe_float(profile.get("near_tech_gap"))
    min_score = max(0.0, active_threshold - near_gap)
    if side not in {"BUY", "SELL"}:
        return False
    if abs_score < min_score:
        return False
    if _safe_float(snapshot.get("ai_prob")) < _safe_float(profile.get("min_ai_prob")):
        return False
    if _safe_float(snapshot.get("setup_quality")) < _safe_float(profile.get("min_setup_quality")):
        return False
    return True


def _historical_cost_candidate(data_dir: Path) -> dict[str, Any]:
    report = _read_json(data_dir / "signal_density_report.json")
    rows = report.get("cost_aware_threshold_optimization")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and _safe_int(row.get("would_pass")) > 0:
            return {
                "prob_threshold": _safe_float(row.get("prob_threshold")),
                "quality_threshold": _safe_float(row.get("quality_threshold")),
                "would_pass": _safe_int(row.get("would_pass")),
                "avg_expected_net_edge_r": _safe_float(row.get("avg_expected_net_edge_r")),
                "avg_expected_cost_bps": _safe_float(row.get("avg_expected_cost_bps")),
                "optimization_score": _safe_float(row.get("optimization_score")),
            }
    return {}


def _build_profiles() -> list[dict[str, Any]]:
    return [
        {
            "name": "meta50_quality60_current_tech",
            "min_ai_prob": 50.0,
            "min_setup_quality": 60.0,
            "near_tech_gap": 0.0,
            "intent": "primary shadow candidate from cost-aware optimization",
        },
        {
            "name": "meta50_quality60_near_tech_5",
            "min_ai_prob": 50.0,
            "min_setup_quality": 60.0,
            "near_tech_gap": 5.0,
            "intent": "watchlist only for candidates within 5 technical-score points",
        },
        {
            "name": "meta45_quality60_current_tech",
            "min_ai_prob": 45.0,
            "min_setup_quality": 60.0,
            "near_tech_gap": 0.0,
            "intent": "density watchlist; lower confidence than primary shadow candidate",
        },
    ]


def build_report(data_dir: Path, tail: int = 5000) -> dict[str, Any]:
    events = _iter_jsonl_tail(data_dir / "paper_events.jsonl", tail)
    no_signal_by_cycle = {
        str(event.get("cycle_id") or ""): event
        for event in events
        if _event_type(event) == "NO_SIGNAL" and event.get("cycle_id")
    }
    signal_events = [event for event in events if _event_type(event) == "SIGNAL_DIAGNOSTIC"]
    snapshots = [_signal_snapshot(event, no_signal_by_cycle) for event in signal_events]
    profiles = _build_profiles()

    profile_rows: list[dict[str, Any]] = []
    for profile in profiles:
        hits = [snapshot for snapshot in snapshots if _passes_profile(snapshot, profile)]
        misses: Counter[str] = Counter()
        for snapshot in snapshots:
            if _passes_profile(snapshot, profile):
                continue
            if str(snapshot.get("side")) not in {"BUY", "SELL"}:
                misses["no_directional_technical_side"] += 1
            elif abs(_safe_float(snapshot.get("technical_score"))) < max(0.0, _safe_float(snapshot.get("active_threshold")) - _safe_float(profile.get("near_tech_gap"))):
                misses["technical_score_below_profile"] += 1
            elif _safe_float(snapshot.get("ai_prob")) < _safe_float(profile.get("min_ai_prob")):
                misses["ai_prob_below_profile"] += 1
            elif _safe_float(snapshot.get("setup_quality")) < _safe_float(profile.get("min_setup_quality")):
                misses["setup_quality_below_profile"] += 1
        profile_rows.append({
            "name": profile["name"],
            "intent": profile["intent"],
            "min_ai_prob": profile["min_ai_prob"],
            "min_setup_quality": profile["min_setup_quality"],
            "near_tech_gap": profile["near_tech_gap"],
            "signals_seen": len(snapshots),
            "shadow_candidates": len(hits),
            "shadow_candidate_rate_pct": round((len(hits) / len(snapshots) * 100.0), 4) if snapshots else 0.0,
            "top_miss_reasons": _top(misses),
            "examples": hits[:5],
        })

    filter_counter = Counter(str(snapshot.get("filter") or "") for snapshot in snapshots if snapshot.get("filter"))
    side_counter = Counter(str(snapshot.get("side") or "") for snapshot in snapshots if snapshot.get("side"))
    scenario_counter = Counter(str(snapshot.get("scenario") or "") for snapshot in snapshots if snapshot.get("scenario"))
    primary = profile_rows[0] if profile_rows else {}
    historical = _historical_cost_candidate(data_dir)
    if _safe_int(primary.get("shadow_candidates")) > 0:
        decision_status = "RECENT_SHADOW_CANDIDATES_FOUND"
        next_action = "inspect_recent_shadow_candidates_before_any_runtime_change"
    elif historical:
        decision_status = "HISTORICAL_OPPORTUNITY_BUT_NO_RECENT_RUNTIME_CANDIDATE"
        next_action = "keep_collecting; leave shadow profile monitored only"
    else:
        decision_status = "NO_SHADOW_OPPORTUNITY"
        next_action = "keep_runtime_thresholds"

    return {
        "report_type": "paper_shadow_threshold_report",
        "diagnostic_only": True,
        "changes_thresholds": False,
        "opens_orders": False,
        "data_dir": str(data_dir),
        "tail_events_read": len(events),
        "decision": {
            "status": decision_status,
            "action": next_action,
            "runtime_threshold_change_allowed": False,
            "paper_order_submission_allowed": False,
        },
        "historical_cost_aware_candidate": historical,
        "recent_signal_summary": {
            "signal_diagnostics": len(snapshots),
            "filters": _top(filter_counter),
            "sides": _top(side_counter),
            "scenarios": _top(scenario_counter, 5),
            "abs_technical_score": _quantiles(abs(_safe_float(s.get("technical_score"))) for s in snapshots),
            "setup_quality": _quantiles(_safe_float(s.get("setup_quality")) for s in snapshots),
            "ai_prob": _quantiles(_safe_float(s.get("ai_prob")) for s in snapshots),
        },
        "profiles": profile_rows,
        "next_steps": [
            "Non cambiare le soglie runtime.",
            "Usa questo report durante il paper-live per vedere se il profilo shadow comincia a trovare candidati recenti.",
            "Se compaiono candidati shadow, controlla esempi, contesto e performance simulata prima di promuovere qualunque soglia.",
        ],
    }


def format_report(report: dict[str, Any]) -> str:
    decision = report["decision"]
    historical = report["historical_cost_aware_candidate"]
    summary = report["recent_signal_summary"]
    lines = [
        "PAPER SHADOW THRESHOLD REPORT",
        f"decision={decision['status']}",
        f"action={decision['action']}",
        "runtime_threshold_change_allowed=False",
        "paper_order_submission_allowed=False",
        "",
        "historical_cost_aware_candidate:",
    ]
    if historical:
        lines.append(
            f"  prob={historical['prob_threshold']:.0f} quality={historical['quality_threshold']:.0f} "
            f"would_pass={historical['would_pass']} avg_expected_net_edge_r={historical['avg_expected_net_edge_r']:.4f}"
        )
    else:
        lines.append("  -")
    lines.extend([
        "",
        "recent_signal_summary:",
        f"  signal_diagnostics={summary['signal_diagnostics']}",
        (
            f"  abs_tech_score median={summary['abs_technical_score']['median']:.2f} "
            f"p75={summary['abs_technical_score']['p75']:.2f} max={summary['abs_technical_score']['max']:.2f}"
        ),
        (
            f"  setup_quality median={summary['setup_quality']['median']:.2f} "
            f"p75={summary['setup_quality']['p75']:.2f} max={summary['setup_quality']['max']:.2f}"
        ),
        (
            f"  ai_prob median={summary['ai_prob']['median']:.2f} "
            f"p75={summary['ai_prob']['p75']:.2f} max={summary['ai_prob']['max']:.2f}"
        ),
        "  filters=" + ", ".join(f"{row['name']}:{row['count']}" for row in summary["filters"]) if summary["filters"] else "  filters=-",
        "",
        "profiles:",
    ])
    for profile in report["profiles"]:
        lines.append(
            f"  {profile['name']}: candidates={profile['shadow_candidates']}/{profile['signals_seen']} "
            f"rate={profile['shadow_candidate_rate_pct']:.4f}%"
        )
        lines.append(f"    intent={profile['intent']}")
        misses = profile["top_miss_reasons"]
        lines.append("    top_miss_reasons=" + (", ".join(f"{row['name']}:{row['count']}" for row in misses) if misses else "-"))
        for example in profile["examples"][:3]:
            lines.append(
                f"    example cycle={example['cycle_id']} side={example['side']} tech={example['technical_score']:.2f} "
                f"q={example['setup_quality']:.2f} p={example['ai_prob']:.2f} scenario={example['scenario']}"
            )
    lines.append("")
    lines.append("next_steps:")
    for step in report["next_steps"]:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only shadow threshold report for candidate optimization.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tail", type=int, default=5000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(Path(args.data_dir), tail=args.tail)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
