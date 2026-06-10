from __future__ import annotations

import argparse
import json
from collections import Counter, deque
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


def _count_values(counter: Counter[str], values: Any) -> None:
    if isinstance(values, list):
        for value in values:
            text = str(value or "").strip()
            if text:
                counter[text] += 1
        return
    text = str(values or "").strip()
    if text:
        counter[text] += 1


def _top(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _quantiles(values: Iterable[float]) -> dict[str, Any]:
    rows = sorted(v for v in values if v == v and v not in {float("inf"), float("-inf")})
    if not rows:
        return {"count": 0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(pct: float) -> float:
        if len(rows) == 1:
            return rows[0]
        idx = int(round((len(rows) - 1) * pct))
        return rows[max(0, min(len(rows) - 1, idx))]

    return {
        "count": len(rows),
        "min": round(rows[0], 6),
        "p25": round(pick(0.25), 6),
        "median": round(pick(0.5), 6),
        "p75": round(pick(0.75), 6),
        "max": round(rows[-1], 6),
        "avg": round(sum(rows) / len(rows), 6),
    }


def _pct(part: int | float, total: int | float) -> float:
    return round((float(part) / float(total) * 100.0), 4) if total else 0.0


def _dist_value(report: dict[str, Any], key: str, metric: str, default: float = 0.0) -> float:
    dist = report.get(key)
    if isinstance(dist, dict):
        return _safe_float(dist.get(metric), default)
    return default


def _first_rows(value: Any, limit: int = 3) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value[:limit] if isinstance(row, dict)]


def _recent_runtime(data_dir: Path, tail: int) -> dict[str, Any]:
    events = _iter_jsonl_tail(data_dir / "paper_events.jsonl", tail)
    cycles = [e for e in events if _event_type(e) == "CYCLE_COMPLETED"]
    signals = [e for e in events if _event_type(e) in {"SIGNAL_DIAGNOSTIC", "NO_SIGNAL"}]
    lsr = [e for e in events if _event_type(e) == "LSR_V2_RUNTIME_CANDIDATE_AUDIT"]
    guarded = [e for e in events if _event_type(e) in {"GUARDED_PAPER_RUNTIME_AUDIT", "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT"}]

    filters: Counter[str] = Counter()
    signal_reasons: Counter[str] = Counter()
    lsr_blockers: Counter[str] = Counter()
    guarded_blockers: Counter[str] = Counter()
    tech_scores: list[float] = []
    setup_quality: list[float] = []
    ai_prob: list[float] = []
    map_scores: list[float] = []
    candidate_age: list[float] = []

    for event in signals:
        _count_values(filters, event.get("dominant_filter") or event.get("diagnostic_filter"))
        _count_values(signal_reasons, event.get("diagnostic_reason"))
        score = event.get("technical_score") if "technical_score" in event else event.get("score")
        tech_scores.append(abs(_safe_float(score)))
        setup_quality.append(_safe_float(event.get("setup_quality")))
        ai_prob.append(_safe_float(event.get("ai_prob")))
    for event in lsr:
        _count_values(lsr_blockers, event.get("blocked_reasons") or event.get("blocked_reason"))
        if event.get("candidate_age_bars") is not None:
            candidate_age.append(_safe_float(event.get("candidate_age_bars")))
    for event in guarded:
        _count_values(guarded_blockers, event.get("blocked_reasons") or event.get("reject_reasons") or event.get("primary_reject_reason"))
        if event.get("map_score") is not None:
            map_scores.append(_safe_float(event.get("map_score")))

    latest_lsr = lsr[-1] if lsr else {}
    return {
        "events_read": len(events),
        "cycles": len(cycles),
        "orders": sum(_safe_int(e.get("orders")) for e in cycles),
        "signals": sum(_safe_int(e.get("signals")) for e in cycles),
        "no_signal": sum(_safe_int(e.get("no_signal")) for e in cycles),
        "errors": sum(_safe_int(e.get("errors")) for e in cycles),
        "signal_filters": _top(filters),
        "signal_reasons": _top(signal_reasons, 5),
        "lsr_blockers": _top(lsr_blockers),
        "guarded_blockers": _top(guarded_blockers),
        "abs_tech_score": _quantiles(tech_scores),
        "setup_quality": _quantiles(setup_quality),
        "ai_prob": _quantiles(ai_prob),
        "map_score": _quantiles(map_scores),
        "lsr_candidate_age_bars": _quantiles(candidate_age),
        "lsr_candidate_ready": sum(1 for e in lsr if bool(e.get("candidate_ready"))),
        "lsr_candidate_fresh_for_submit": sum(1 for e in lsr if bool(e.get("candidate_fresh_for_submit"))),
        "latest_lsr_candidate_age_bars": _safe_int(latest_lsr.get("candidate_age_bars")),
        "latest_lsr_max_submit_age_bars": _safe_int(latest_lsr.get("max_submit_candidate_age_bars")),
    }


def _signal_diagnostics(report: dict[str, Any]) -> dict[str, Any]:
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    filters = report.get("dominant_filters") if isinstance(report.get("dominant_filters"), dict) else {}
    thresholds = report.get("thresholds") if isinstance(report.get("thresholds"), dict) else {}
    quasi = _first_rows(report.get("top_quasi_signals"), 5)
    return {
        "status": report.get("status") or "UNKNOWN",
        "counts": counts,
        "dominant_filters": filters,
        "thresholds": thresholds,
        "conclusions": report.get("conclusions") if isinstance(report.get("conclusions"), list) else [],
        "top_quasi_summary": [
            {
                "symbol": row.get("symbol"),
                "side": row.get("intended_side"),
                "filter": row.get("dominant_filter"),
                "tech_score": _safe_float(row.get("technical_score")),
                "setup_quality": _safe_float(row.get("setup_quality")),
                "ai_prob": _safe_float(row.get("ai_prob")),
                "reason": row.get("diagnostic_reason"),
            }
            for row in quasi
        ],
    }


def _signal_density(report: dict[str, Any]) -> dict[str, Any]:
    funnel = report.get("funnel") if isinstance(report.get("funnel"), dict) else {}
    cost_candidates = _first_rows(report.get("cost_aware_threshold_optimization"), 5)
    threshold_sweep = _first_rows(report.get("threshold_sweep"), 8)
    return {
        "funnel": funnel,
        "thresholds": report.get("thresholds") if isinstance(report.get("thresholds"), dict) else {},
        "probability_distribution": report.get("probability_distribution") if isinstance(report.get("probability_distribution"), dict) else {},
        "setup_quality_distribution": report.get("setup_quality_distribution") if isinstance(report.get("setup_quality_distribution"), dict) else {},
        "cost_aware_top": [
            {
                "prob_threshold": _safe_float(row.get("prob_threshold")),
                "quality_threshold": _safe_float(row.get("quality_threshold")),
                "would_pass": _safe_int(row.get("would_pass")),
                "avg_expected_net_edge_r": _safe_float(row.get("avg_expected_net_edge_r")),
                "avg_expected_cost_bps": _safe_float(row.get("avg_expected_cost_bps")),
                "optimization_score": _safe_float(row.get("optimization_score")),
            }
            for row in cost_candidates
        ],
        "density_sweep_sample": [
            {
                "prob_threshold": _safe_float(row.get("prob_threshold")),
                "quality_threshold": _safe_float(row.get("quality_threshold")),
                "would_pass": _safe_int(row.get("would_pass")),
                "pass_rate_pct": _safe_float(row.get("pass_rate_pct")),
            }
            for row in threshold_sweep
        ],
        "rejection_reasons": report.get("rejection_reasons") if isinstance(report.get("rejection_reasons"), dict) else {},
    }


def _unlock_rejections(report: dict[str, Any]) -> dict[str, Any]:
    btc = report.get("btc_focus") if isinstance(report.get("btc_focus"), dict) else {}
    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    metrics = btc.get("metrics") if isinstance(btc.get("metrics"), dict) else {}
    return {
        "status": report.get("status") or "UNKNOWN",
        "counts": report.get("counts") if isinstance(report.get("counts"), dict) else {},
        "decision": decision,
        "rejection_reasons": report.get("rejection_reasons") if isinstance(report.get("rejection_reasons"), dict) else {},
        "btc_evaluated": _safe_int(btc.get("evaluated")),
        "btc_accepted": _safe_int(btc.get("accepted")),
        "btc_dominant_filters": btc.get("dominant_filters") if isinstance(btc.get("dominant_filters"), dict) else {},
        "btc_abs_technical_score": metrics.get("abs_technical_score") if isinstance(metrics.get("abs_technical_score"), dict) else {},
        "btc_setup_quality": metrics.get("setup_quality") if isinstance(metrics.get("setup_quality"), dict) else {},
        "btc_ai_prob": metrics.get("ai_prob") if isinstance(metrics.get("ai_prob"), dict) else {},
        "warnings": report.get("warnings") if isinstance(report.get("warnings"), list) else [],
    }


def _lsr_v2(report: dict[str, Any]) -> dict[str, Any]:
    criteria = report.get("criteria") if isinstance(report.get("criteria"), dict) else {}
    settings = report.get("settings") if isinstance(report.get("settings"), dict) else {}
    summaries = report.get("window_summaries") if isinstance(report.get("window_summaries"), list) else []
    conservative = [row for row in summaries if isinstance(row, dict) and str(row.get("cost_model")) == "conservative"]
    severe = [row for row in summaries if isinstance(row, dict) and str(row.get("cost_model")) == "severe"]
    return {
        "status": report.get("status") or "UNKNOWN",
        "decision": report.get("decision") or "UNKNOWN",
        "promotion_ready": bool(report.get("promotion_ready")),
        "criteria": criteria,
        "settings": {
            "min_closed_trades": _safe_int(settings.get("min_closed_trades"), 30),
            "preferred_closed_trades": _safe_int(settings.get("preferred_closed_trades"), 50),
            "require_severe_cost_survival": bool(settings.get("require_severe_cost_survival")),
            "max_top_trade_concentration": _safe_float(settings.get("max_top_trade_concentration"), 0.45),
            "target_rr": _safe_float(settings.get("target_rr"), 2.0),
            "max_cost_to_r": _safe_float(settings.get("max_cost_to_r"), 0.35),
        },
        "conservative_windows": [
            {
                "window": row.get("window_label"),
                "closed_trades": _safe_int(row.get("closed_trades")),
                "avg_r_post_cost": _safe_float(row.get("avg_r_post_cost")),
                "sum_r_post_cost": _safe_float(row.get("sum_r_post_cost")),
                "win_rate": _safe_float(row.get("win_rate")),
                "top_trade_concentration": _safe_float(row.get("top_trade_concentration")),
            }
            for row in conservative
        ],
        "severe_negative_windows": sum(1 for row in severe if _safe_float(row.get("avg_r_post_cost")) < 0),
    }


def _opportunity_matrix(sections: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = sections["recent_runtime"]
    signal_diag = sections["paper_signal_diagnostics"]
    density = sections["signal_density"]
    unlock = sections["paper_unlock_rejections"]
    lsr = sections["lsr_v2"]

    matrix: list[dict[str, Any]] = []
    cost_top = density.get("cost_aware_top") or []
    best_cost = cost_top[0] if cost_top else {}
    if best_cost and _safe_int(best_cost.get("would_pass")) > 0:
        matrix.append({
            "area": "meta_probability_setup_quality",
            "proposal": f"shadow_test_prob_{_safe_float(best_cost.get('prob_threshold')):.0f}_quality_{_safe_float(best_cost.get('quality_threshold')):.0f}",
            "action": "SHADOW_TEST_ONLY",
            "evidence": (
                f"cost-aware sweep: would_pass={_safe_int(best_cost.get('would_pass'))}, "
                f"avg_expected_net_edge_r={_safe_float(best_cost.get('avg_expected_net_edge_r')):.4f}"
            ),
            "risk": "Model probability appears compressed around 50; runtime threshold changes could admit neutral model outputs.",
        })

    dominant_filters = signal_diag.get("dominant_filters") if isinstance(signal_diag.get("dominant_filters"), dict) else {}
    tech_low = _safe_int(dominant_filters.get("TECH_SCORE_LOW"))
    diagnostics = _safe_int((signal_diag.get("counts") or {}).get("diagnostics"))
    matrix.append({
        "area": "technical_score_gate",
        "proposal": "keep_current_trending_threshold_60",
        "action": "KEEP_RUNTIME",
        "evidence": f"TECH_SCORE_LOW={tech_low}/{diagnostics} diagnostics; recent median abs tech score={runtime['abs_tech_score']['median']:.2f}.",
        "risk": "Lowering the technical gate now would mostly increase weak HOLD/no-side samples, not confirmed setups.",
    })

    decision = unlock.get("decision") if isinstance(unlock.get("decision"), dict) else {}
    matrix.append({
        "area": "map_score_guarded_bridge",
        "proposal": "keep_map_score_65_79_guard",
        "action": "KEEP_RUNTIME",
        "evidence": f"unlock decision={decision.get('status') or 'UNKNOWN'}; BTC accepted={unlock.get('btc_accepted')}/{unlock.get('btc_evaluated')}.",
        "risk": "Current blockers are no_intended_side/WAIT/map_score_outside_65_79; relaxing map score would not fix side confirmation.",
    })

    latest_age = _safe_int(runtime.get("latest_lsr_candidate_age_bars"))
    max_age = _safe_int(runtime.get("latest_lsr_max_submit_age_bars"))
    matrix.append({
        "area": "lsr_v2_anti_stale",
        "proposal": f"keep_max_submit_candidate_age_bars_{max_age or 3}",
        "action": "KEEP_RUNTIME",
        "evidence": f"latest candidate age={latest_age} bars; fresh_for_submit={runtime.get('lsr_candidate_fresh_for_submit')}/{runtime.get('lsr_candidate_ready')}.",
        "risk": "Relaxing anti-stale enough to pass the current candidate would allow very old setups.",
    })

    criteria = lsr.get("criteria") if isinstance(lsr.get("criteria"), dict) else {}
    blockers = criteria.get("blockers") if isinstance(criteria.get("blockers"), list) else []
    matrix.append({
        "area": "lsr_v2_promotion",
        "proposal": "keep_diagnostic_until_sample_and_cost_survival_pass",
        "action": "KEEP_RUNTIME",
        "evidence": (
            f"promotion_ready={lsr.get('promotion_ready')}; closed_trades={criteria.get('closed_trades', 0)}; "
            f"blockers={','.join(str(x) for x in blockers) or '-'}"
        ),
        "risk": "Backtest edge is promising but sample is still below promotion criteria and severe cost survival failed.",
    })
    return matrix


def _decision(sections: dict[str, Any], matrix: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = sections["recent_runtime"]
    density = sections["signal_density"]
    lsr = sections["lsr_v2"]
    cost_top = density.get("cost_aware_top") or []
    has_shadow_candidate = bool(cost_top and _safe_int(cost_top[0].get("would_pass")) > 0)
    runtime_orders = _safe_int(runtime.get("orders"))
    lsr_ready = bool(lsr.get("promotion_ready"))
    if has_shadow_candidate:
        status = "SHADOW_OPTIMIZATION_AVAILABLE"
        action = "create_shadow_candidate_profile; do_not_change_runtime_thresholds_yet"
    else:
        status = "NO_SAFE_THRESHOLD_MOVE"
        action = "keep_runtime_thresholds; collect_more_paper_live_data"
    return {
        "status": status,
        "action": action,
        "runtime_threshold_change_allowed": False,
        "shadow_threshold_test_allowed": has_shadow_candidate,
        "lsr_v2_runtime_promotion_allowed": lsr_ready,
        "recent_runtime_orders_in_tail": runtime_orders,
        "matrix_actions": Counter(row["action"] for row in matrix),
    }


def _next_steps(decision: dict[str, Any]) -> list[str]:
    steps = [
        "Mantieni paper-live con soglie runtime attuali.",
        "Aggiungi solo un profilo shadow per meta_prob/setup_quality, senza submit ordini.",
        "Continua a raccogliere paper-live fino ad almeno 20-30 trade runtime reali prima di promuovere soglie.",
        "Non allargare anti-stale LSR-v2: aspetta candidate freschi.",
    ]
    if not decision.get("shadow_threshold_test_allowed"):
        steps[1] = "Non attivare ancora profili shadow di soglia: i dati non mostrano un candidato robusto."
    return steps


def build_report(data_dir: Path, tail: int = 5000) -> dict[str, Any]:
    sections = {
        "recent_runtime": _recent_runtime(data_dir, tail),
        "paper_signal_diagnostics": _signal_diagnostics(_read_json(data_dir / "paper_signal_diagnostics_report.json")),
        "signal_density": _signal_density(_read_json(data_dir / "signal_density_report.json")),
        "paper_unlock_rejections": _unlock_rejections(_read_json(data_dir / "paper_unlock_rejection_report.json")),
        "lsr_v2": _lsr_v2(_read_json(data_dir / "lsr_v2_backtest_matrix_report.json")),
    }
    matrix = _opportunity_matrix(sections)
    decision = _decision(sections, matrix)
    return {
        "report_type": "paper_strategy_opportunity_audit",
        "diagnostic_only": True,
        "changes_thresholds": False,
        "opens_orders": False,
        "data_dir": str(data_dir),
        "tail_events_read": sections["recent_runtime"]["events_read"],
        "decision": decision,
        "sections": sections,
        "opportunity_matrix": matrix,
        "next_steps": _next_steps(decision),
    }


def _fmt_counter_dict(data: dict[str, Any], limit: int = 6) -> str:
    if not isinstance(data, dict) or not data:
        return "-"
    rows = sorted(data.items(), key=lambda item: _safe_float(item[1]), reverse=True)[:limit]
    return ", ".join(f"{key}:{value}" for key, value in rows)


def format_report(report: dict[str, Any]) -> str:
    decision = report["decision"]
    sections = report["sections"]
    runtime = sections["recent_runtime"]
    signal_diag = sections["paper_signal_diagnostics"]
    density = sections["signal_density"]
    unlock = sections["paper_unlock_rejections"]
    lsr = sections["lsr_v2"]
    funnel = density.get("funnel") if isinstance(density.get("funnel"), dict) else {}
    criteria = lsr.get("criteria") if isinstance(lsr.get("criteria"), dict) else {}

    lines = [
        "PAPER STRATEGY OPPORTUNITY AUDIT",
        f"decision={decision['status']}",
        f"action={decision['action']}",
        "runtime_threshold_change_allowed=False",
        f"shadow_threshold_test_allowed={decision['shadow_threshold_test_allowed']}",
        "",
        "recent_runtime:",
        (
            f"  cycles={runtime['cycles']} signals={runtime['signals']} orders={runtime['orders']} "
            f"no_signal={runtime['no_signal']} errors={runtime['errors']}"
        ),
        (
            f"  abs_tech_score median={runtime['abs_tech_score']['median']:.2f} "
            f"p75={runtime['abs_tech_score']['p75']:.2f} max={runtime['abs_tech_score']['max']:.2f}"
        ),
        (
            f"  lsr_age latest={runtime['latest_lsr_candidate_age_bars']} "
            f"max_allowed={runtime['latest_lsr_max_submit_age_bars']} "
            f"fresh={runtime['lsr_candidate_fresh_for_submit']}/{runtime['lsr_candidate_ready']}"
        ),
        "  filters=" + ", ".join(f"{row['name']}:{row['count']}" for row in runtime["signal_filters"]) if runtime["signal_filters"] else "  filters=-",
        "",
        "historical_signal_diagnostics:",
        (
            f"  status={signal_diag['status']} diagnostics={_safe_int((signal_diag.get('counts') or {}).get('diagnostics'))} "
            f"near_candidates={_safe_int((signal_diag.get('counts') or {}).get('near_candidates'))} "
            f"orders_submitted={_safe_int((signal_diag.get('counts') or {}).get('orders_submitted'))}"
        ),
        "  dominant_filters=" + _fmt_counter_dict(signal_diag.get("dominant_filters") or {}),
        "",
        "signal_density:",
        (
            f"  bars={_safe_int(funnel.get('bars_evaluated'))} technical_candidates={_safe_int(funnel.get('technical_candidates'))} "
            f"cost_aware_pass={_safe_int(funnel.get('cost_aware_pass'))} meta_accepted={_safe_int(funnel.get('meta_accepted'))}"
        ),
        (
            f"  probability median={_dist_value(density, 'probability_distribution', 'median'):.2f} "
            f"p90={_dist_value(density, 'probability_distribution', 'p90'):.2f} "
            f"max={_dist_value(density, 'probability_distribution', 'max'):.2f}"
        ),
        "",
        "paper_unlock_rejections:",
        (
            f"  status={unlock['status']} btc_accepted={unlock['btc_accepted']}/{unlock['btc_evaluated']} "
            f"decision={(unlock.get('decision') or {}).get('status') or 'UNKNOWN'}"
        ),
        "  reasons=" + _fmt_counter_dict(unlock.get("rejection_reasons") or {}),
        "",
        "lsr_v2_backtest:",
        (
            f"  status={lsr['status']} promotion_ready={lsr['promotion_ready']} decision={lsr['decision']} "
            f"closed_trades={criteria.get('closed_trades', 0)} weighted_avg_r={_safe_float(criteria.get('weighted_avg_r_post_cost')):.4f}"
        ),
        "  blockers=" + ",".join(str(x) for x in criteria.get("blockers", [])) if isinstance(criteria.get("blockers"), list) else "  blockers=-",
        "",
        "opportunity_matrix:",
    ]
    for row in report["opportunity_matrix"]:
        lines.append(f"  [{row['action']}] {row['area']}: {row['proposal']}")
        lines.append(f"    evidence={row['evidence']}")
        lines.append(f"    risk={row['risk']}")
    lines.append("")
    lines.append("next_steps:")
    for step in report["next_steps"]:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only threshold and strategy opportunity audit for paper-live optimization.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tail", type=int, default=5000, help="Recent paper_events.jsonl rows to inspect.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()
    report = build_report(Path(args.data_dir), tail=args.tail)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
