from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable


BULLISH_PATTERNS = {
    "fake_breakdown_reclaim",
    "hammer",
    "bullish_pin_bar",
    "bullish_inside_bar",
    "inside_bar",
}


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


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "")


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        "median": round(pick(0.5), 6),
        "p75": round(pick(0.75), 6),
        "max": round(rows[-1], 6),
        "avg": round(sum(rows) / len(rows), 6),
    }


def _top(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _cycle_map(events: list[dict[str, Any]], event_type: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for event in events:
        if _event_type(event) == event_type and event.get("cycle_id"):
            out[str(event.get("cycle_id"))] = event
    return out


def _support_distance_pct(scenario: dict[str, Any], structure: dict[str, Any]) -> float:
    levels = scenario.get("levels") if isinstance(scenario.get("levels"), dict) else {}
    direct = _safe_float(levels.get("dist_to_support_pct"), -1.0)
    if direct >= 0:
        return direct
    price = _safe_float(structure.get("price"))
    s_levels = structure.get("levels") if isinstance(structure.get("levels"), dict) else {}
    swing_low = _safe_float(s_levels.get("last_swing_low"))
    if price > 0 and swing_low > 0:
        return abs(price - swing_low) / price * 100.0
    return 999.0


def _range_pos(scenario: dict[str, Any], structure: dict[str, Any]) -> float:
    levels = scenario.get("levels") if isinstance(scenario.get("levels"), dict) else {}
    if "range_pos_400" in levels:
        return _safe_float(levels.get("range_pos_400"))
    context = structure.get("context") if isinstance(structure.get("context"), dict) else {}
    return _safe_float(context.get("range_pos_400"), 0.5)


def _patterns(pattern_event: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("patterns", "bullish_patterns"):
        for value in _as_list(pattern_event.get(key)):
            text = str(value or "")
            if text and text not in out:
                out.append(text)
    return out


def _has_bullish_pattern(pattern_event: dict[str, Any]) -> bool:
    bias = str(pattern_event.get("pattern_bias") or pattern_event.get("candlestick_bias") or "").upper()
    if bias == "BUY":
        return True
    return any(pattern in BULLISH_PATTERNS for pattern in _patterns(pattern_event))


def _context_candidate(snapshot: dict[str, Any]) -> bool:
    scenario = str(snapshot.get("scenario") or "").upper()
    current_zone = str(snapshot.get("current_zone") or "").upper()
    location = str(snapshot.get("price_location") or "").upper()
    return bool(
        snapshot["support_distance_pct"] <= 0.25
        and snapshot["range_pos_400"] <= 0.12
        and (
            scenario in {"BUY_REJECTION_CANDIDATE", "NEAR_SUPPORT"}
            or current_zone == "RANGE_EXTREME_LOW"
            or "DEMAND" in location
        )
    )


def _watchlist_candidate(snapshot: dict[str, Any]) -> bool:
    return bool(
        _context_candidate(snapshot)
        and snapshot["candlestick_score"] >= 55.0
        and snapshot["has_bullish_pattern"]
    )


def _strict_shadow_candidate(snapshot: dict[str, Any]) -> bool:
    return bool(
        _watchlist_candidate(snapshot)
        and snapshot["volume_ratio_20"] >= 0.60
        and snapshot["confirmation_close"]
        and snapshot["map_score"] >= 50.0
        and snapshot["structure_state"] in {"CONFIRMATION", "CONTEXT"}
    )


def _miss_reasons(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _context_candidate(snapshot):
        reasons.append("not_near_support_context")
    if snapshot["candlestick_score"] < 55.0 or not snapshot["has_bullish_pattern"]:
        reasons.append("bullish_pattern_not_strong")
    if snapshot["volume_ratio_20"] < 0.60:
        reasons.append("volume_confirmation_missing")
    if not snapshot["confirmation_close"]:
        reasons.append("confirmation_close_missing")
    if snapshot["map_score"] < 50.0:
        reasons.append("map_score_below_strict_shadow_50")
    if snapshot["structure_state"] not in {"CONFIRMATION", "CONTEXT"}:
        reasons.append(f"structure_state_not_ready:{snapshot['structure_state']}")
    return reasons


def _snapshot(
    cycle_id: str,
    signal: dict[str, Any],
    scenario: dict[str, Any],
    pattern: dict[str, Any],
    structure: dict[str, Any],
    guarded: dict[str, Any],
    no_signal: dict[str, Any],
) -> dict[str, Any]:
    candle = scenario.get("candle") if isinstance(scenario.get("candle"), dict) else {}
    context = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    missing_structure = _as_list(structure.get("missing_confirmation")) or _as_list(no_signal.get("market_structure_missing_confirmation"))
    missing_pattern = _as_list(pattern.get("missing_confirmations"))
    range_pos = _range_pos(scenario, structure)
    support_distance = _support_distance_pct(scenario, structure)
    patterns = _patterns(pattern)
    structure_state = str(guarded.get("runtime_structure_state") or "").upper()
    if not structure_state:
        summary = str(structure.get("confirmation_summary") or no_signal.get("market_structure_confirmation") or "").upper()
        structure_state = "CONFIRMATION" if "CONFIRM" in summary and "NO_" not in summary else "NO_STRUCTURE"
    snapshot = {
        "cycle_id": cycle_id,
        "symbol": signal.get("symbol") or scenario.get("symbol") or no_signal.get("symbol"),
        "candle_ts": signal.get("candle_ts") or scenario.get("candle_ts") or no_signal.get("candle_ts"),
        "ts": signal.get("ts") or scenario.get("ts") or no_signal.get("ts"),
        "last_price": _safe_float(signal.get("last_price") or scenario.get("last_price") or structure.get("price")),
        "engine_intended_side": signal.get("intended_side") or no_signal.get("verdict"),
        "technical_score": _safe_float(signal.get("technical_score") if "technical_score" in signal else signal.get("score")),
        "filter": signal.get("dominant_filter") or signal.get("diagnostic_filter") or no_signal.get("diagnostic_filter"),
        "reason": signal.get("diagnostic_reason") or no_signal.get("diagnostic_reason"),
        "scenario": scenario.get("scenario") or no_signal.get("scenario") or "-",
        "scenario_alignment": scenario.get("scenario_alignment") or no_signal.get("scenario_alignment") or "-",
        "scenario_bias": scenario.get("directional_bias") or scenario.get("scenario_directional_bias") or no_signal.get("scenario_directional_bias") or "-",
        "scenario_recommendation": scenario.get("recommendation") or no_signal.get("scenario_recommendation") or "-",
        "current_zone": scenario.get("current_zone") or no_signal.get("scenario_current_zone") or "-",
        "price_location": structure.get("price_location") or no_signal.get("market_structure_location") or "-",
        "range_pos_400": range_pos,
        "support_distance_pct": support_distance,
        "near_support": bool(context.get("near_support") or "near_support" in _as_list(pattern.get("confirmations"))),
        "lower_wick_ratio": _safe_float(candle.get("lower_wick_ratio") or (pattern.get("candle_metrics") or {}).get("lower_wick_ratio")),
        "body_ratio": _safe_float(candle.get("body_ratio") or (pattern.get("candle_metrics") or {}).get("body_ratio")),
        "volume_ratio_20": _safe_float(candle.get("volume_ratio_20") or (pattern.get("candle_metrics") or {}).get("volume_ratio_20")),
        "patterns": patterns,
        "has_bullish_pattern": _has_bullish_pattern(pattern),
        "candlestick_score": _safe_float(pattern.get("pattern_score") or guarded.get("candlestick_score")),
        "candlestick_bias": pattern.get("pattern_bias") or guarded.get("candlestick_bias") or "-",
        "candlestick_integration": pattern.get("scenario_integration") or no_signal.get("candlestick_integration") or "-",
        "pattern_missing_confirmations": missing_pattern,
        "map_score": _safe_float(structure.get("map_score") or guarded.get("map_score")),
        "confirmation_close": bool(structure.get("confirmation_close")),
        "market_structure_confirmation": structure.get("confirmation_summary") or no_signal.get("market_structure_confirmation") or "-",
        "market_structure_missing_confirmation": missing_structure,
        "structure_state": structure_state,
        "guarded_reject_reasons": _as_list(guarded.get("reject_reasons")) or _as_list(guarded.get("blocked_reasons")),
    }
    snapshot["context_candidate"] = _context_candidate(snapshot)
    snapshot["watchlist_candidate"] = _watchlist_candidate(snapshot)
    snapshot["strict_shadow_candidate"] = _strict_shadow_candidate(snapshot)
    snapshot["strict_miss_reasons"] = _miss_reasons(snapshot)
    return snapshot


def build_report(data_dir: Path, tail: int = 5000) -> dict[str, Any]:
    events = _iter_jsonl_tail(data_dir / "paper_events.jsonl", tail)
    signals = _cycle_map(events, "SIGNAL_DIAGNOSTIC")
    scenarios = _cycle_map(events, "CRYPTO_SCENARIO_DIAGNOSTIC")
    patterns = _cycle_map(events, "CANDLESTICK_PATTERN_DIAGNOSTIC")
    structures = _cycle_map(events, "MARKET_STRUCTURE_MAP_DIAGNOSTIC")
    guarded = _cycle_map(events, "GUARDED_PAPER_RUNTIME_AUDIT")
    no_signals = _cycle_map(events, "NO_SIGNAL")
    cycle_ids = sorted(set(signals) | set(scenarios) | set(patterns) | set(structures) | set(no_signals))
    snapshots = [
        _snapshot(
            cycle_id,
            signals.get(cycle_id, {}),
            scenarios.get(cycle_id, {}),
            patterns.get(cycle_id, {}),
            structures.get(cycle_id, {}),
            guarded.get(cycle_id, {}),
            no_signals.get(cycle_id, {}),
        )
        for cycle_id in cycle_ids
    ]
    context = [row for row in snapshots if row["context_candidate"]]
    watchlist = [row for row in snapshots if row["watchlist_candidate"]]
    strict = [row for row in snapshots if row["strict_shadow_candidate"]]
    miss_counter: Counter[str] = Counter()
    for row in watchlist:
        if not row["strict_shadow_candidate"]:
            miss_counter.update(row["strict_miss_reasons"])
    scenario_counter = Counter(str(row["scenario"]) for row in snapshots if row.get("scenario"))
    pattern_counter: Counter[str] = Counter()
    for row in watchlist:
        pattern_counter.update(row["patterns"])
    if strict:
        status = "STRICT_SHADOW_CANDIDATES_FOUND"
        action = "inspect_strict_shadow_candidates_before_any_runtime_change"
    elif watchlist:
        status = "WATCHLIST_ONLY_SUPPORT_REJECTION_CONTEXT"
        action = "monitor_support_rejection; wait_for_structure_or_volume_confirmation"
    else:
        status = "NO_SUPPORT_REJECTION_CONTEXT"
        action = "keep_collecting"
    return {
        "report_type": "paper_support_rejection_shadow_report",
        "diagnostic_only": True,
        "changes_thresholds": False,
        "opens_orders": False,
        "data_dir": str(data_dir),
        "tail_events_read": len(events),
        "decision": {
            "status": status,
            "action": action,
            "runtime_threshold_change_allowed": False,
            "paper_order_submission_allowed": False,
        },
        "counts": {
            "cycles_evaluated": len(snapshots),
            "context_candidates": len(context),
            "watchlist_candidates": len(watchlist),
            "strict_shadow_candidates": len(strict),
        },
        "distributions": {
            "watchlist_map_score": _quantiles(row["map_score"] for row in watchlist),
            "watchlist_volume_ratio_20": _quantiles(row["volume_ratio_20"] for row in watchlist),
            "watchlist_support_distance_pct": _quantiles(row["support_distance_pct"] for row in watchlist),
            "watchlist_range_pos_400": _quantiles(row["range_pos_400"] for row in watchlist),
            "watchlist_candlestick_score": _quantiles(row["candlestick_score"] for row in watchlist),
        },
        "top_reasons": {
            "scenarios": _top(scenario_counter),
            "watchlist_patterns": _top(pattern_counter),
            "strict_missing": _top(miss_counter),
        },
        "examples": {
            "strict_shadow": strict[-5:],
            "watchlist": watchlist[-8:],
        },
        "next_steps": [
            "Non aprire ordini da questo report: e solo shadow.",
            "Se strict_shadow_candidates resta 0, non promuovere il profilo BUY support-rejection.",
            "Il primo miglioramento utile e attendere confirmation_close, map_score >= 50 e volume_ratio_20 >= 0.60.",
        ],
    }


def format_report(report: dict[str, Any]) -> str:
    decision = report["decision"]
    counts = report["counts"]
    dist = report["distributions"]
    lines = [
        "PAPER SUPPORT REJECTION SHADOW REPORT",
        f"decision={decision['status']}",
        f"action={decision['action']}",
        "runtime_threshold_change_allowed=False",
        "paper_order_submission_allowed=False",
        "",
        "counts:",
        (
            f"  cycles={counts['cycles_evaluated']} context={counts['context_candidates']} "
            f"watchlist={counts['watchlist_candidates']} strict_shadow={counts['strict_shadow_candidates']}"
        ),
        "",
        "watchlist_distributions:",
        (
            f"  map_score median={dist['watchlist_map_score']['median']:.2f} "
            f"p75={dist['watchlist_map_score']['p75']:.2f} max={dist['watchlist_map_score']['max']:.2f}"
        ),
        (
            f"  volume_ratio_20 median={dist['watchlist_volume_ratio_20']['median']:.3f} "
            f"p75={dist['watchlist_volume_ratio_20']['p75']:.3f} max={dist['watchlist_volume_ratio_20']['max']:.3f}"
        ),
        (
            f"  support_distance_pct median={dist['watchlist_support_distance_pct']['median']:.3f} "
            f"p75={dist['watchlist_support_distance_pct']['p75']:.3f} max={dist['watchlist_support_distance_pct']['max']:.3f}"
        ),
        (
            f"  range_pos_400 median={dist['watchlist_range_pos_400']['median']:.4f} "
            f"p75={dist['watchlist_range_pos_400']['p75']:.4f} max={dist['watchlist_range_pos_400']['max']:.4f}"
        ),
        "",
        "top_reasons:",
    ]
    for group, rows in report["top_reasons"].items():
        lines.append(f"  {group}:")
        if rows:
            for row in rows:
                lines.append(f"    {row['name']}: {row['count']}")
        else:
            lines.append("    -")
    lines.append("")
    lines.append("watchlist_examples:")
    for row in report["examples"]["watchlist"][-5:]:
        lines.append(
            f"  {row['cycle_id']} {row['candle_ts']} price={row['last_price']:.2f} "
            f"pattern_score={row['candlestick_score']:.1f} map={row['map_score']:.1f} "
            f"vol={row['volume_ratio_20']:.3f} range={row['range_pos_400']:.4f}"
        )
        lines.append(
            f"    patterns={','.join(row['patterns']) or '-'} "
            f"missing={','.join(row['strict_miss_reasons']) or '-'}"
        )
    if report["examples"]["strict_shadow"]:
        lines.append("")
        lines.append("strict_shadow_examples:")
        for row in report["examples"]["strict_shadow"][-5:]:
            lines.append(f"  {row['cycle_id']} {row['candle_ts']} price={row['last_price']:.2f}")
    lines.append("")
    lines.append("next_steps:")
    for step in report["next_steps"]:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BUY support-rejection shadow report.")
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
