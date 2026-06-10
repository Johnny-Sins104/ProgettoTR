from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable


ORDER_EVENTS = {
    "PAPER_ORDER_SUBMITTED",
    "PAPER_POSITION_OPENED",
    "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
    "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
    "LSR_V2_RUNTIME_PAPER_ORDER_SUBMITTED",
}


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


def _positions(state: dict[str, Any], status: str) -> list[dict[str, Any]]:
    raw = state.get("positions")
    if isinstance(raw, dict):
        rows = [p for p in raw.values() if isinstance(p, dict)]
    elif isinstance(raw, list):
        rows = [p for p in raw if isinstance(p, dict)]
    else:
        rows = []
    expected = status.upper()
    return [p for p in rows if str(p.get("status") or "").upper() == expected]


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "")


def _last(events: Iterable[dict[str, Any]], *event_types: str) -> dict[str, Any]:
    wanted = set(event_types)
    for event in reversed(list(events)):
        if _event_type(event) in wanted:
            return event
    return {}


def _count_reasons(counter: Counter[str], values: Any) -> None:
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
    return [{"reason": reason, "count": count} for reason, count in counter.most_common(limit)]


def _engine_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest = _last(events, "CYCLE_STARTED", "CYCLE_COMPLETED", "MAX_CYCLES_REACHED", "ENGINE_STOPPED")
    latest_type = _event_type(latest)
    max_cycles = _last(events, "MAX_CYCLES_REACHED")
    if latest_type == "ENGINE_STOPPED":
        state = "STOPPED"
    elif latest_type == "MAX_CYCLES_REACHED":
        state = "STOPPING_MAX_CYCLES"
    elif latest_type in {"CYCLE_STARTED", "CYCLE_COMPLETED"}:
        state = "RECENT_CYCLES_SEEN"
    else:
        state = "UNKNOWN"
    return {
        "state": state,
        "latest_event_type": latest_type or "-",
        "latest_ts": latest.get("ts") or latest.get("created_at") or "-",
        "max_cycles_reached": bool(max_cycles),
        "max_cycles": _safe_int(max_cycles.get("max_cycles")) if max_cycles else 0,
        "completed_cycles": _safe_int(max_cycles.get("completed_cycles")) if max_cycles else 0,
    }


def build_report(data_dir: Path, tail: int = 2000) -> dict[str, Any]:
    events_path = data_dir / "paper_events.jsonl"
    events = _iter_jsonl_tail(events_path, tail)
    state = _read_json(data_dir / "paper_state.json")
    status = _read_json(data_dir / "paper_status.json")

    completed_cycles = [e for e in events if _event_type(e) == "CYCLE_COMPLETED"]
    last_cycle = completed_cycles[-1] if completed_cycles else {}
    last_signal = _last(events, "SIGNAL_DIAGNOSTIC")
    last_no_signal = _last(events, "NO_SIGNAL")
    signal_source = last_signal or last_no_signal
    last_lsr = _last(events, "LSR_V2_RUNTIME_CANDIDATE_AUDIT")
    last_lsr_bridge = _last(events, "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT")
    last_guarded = _last(events, "GUARDED_PAPER_RUNTIME_AUDIT", "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT")
    last_market = _last(events, "MARKET_DATA_LIVE_USED", "MARKET_DATA_FALLBACK_USED", "MARKET_DATA_ERROR")
    last_asset = _last(events, "ASSET_SCANNED")

    signal_filters: Counter[str] = Counter()
    no_signal_reasons: Counter[str] = Counter()
    lsr_reasons: Counter[str] = Counter()
    guarded_reasons: Counter[str] = Counter()
    unlock_reasons: Counter[str] = Counter()
    event_counts: Counter[str] = Counter(_event_type(e) for e in events if _event_type(e))

    for event in events:
        et = _event_type(event)
        if et in {"SIGNAL_DIAGNOSTIC", "NO_SIGNAL"}:
            _count_reasons(signal_filters, event.get("dominant_filter") or event.get("diagnostic_filter"))
            _count_reasons(no_signal_reasons, event.get("diagnostic_reason"))
        if et in {"LSR_V2_RUNTIME_CANDIDATE_AUDIT", "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"}:
            _count_reasons(lsr_reasons, event.get("blocked_reasons") or event.get("blocked_reason"))
        if et in {"GUARDED_PAPER_RUNTIME_AUDIT", "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT"}:
            _count_reasons(guarded_reasons, event.get("blocked_reasons") or event.get("reject_reasons") or event.get("primary_reject_reason"))
        if et == "PAPER_UNLOCK_EVALUATED":
            _count_reasons(unlock_reasons, event.get("reason"))

    order_event_count = sum(event_counts.get(name, 0) for name in ORDER_EVENTS)
    open_positions = _positions(state, "OPEN")

    report = {
        "files": {
            "events": str(events_path),
            "state": str(data_dir / "paper_state.json"),
            "status": str(data_dir / "paper_status.json"),
        },
        "tail_events_read": len(events),
        "engine": _engine_state(events),
        "state": {
            "mode": status.get("mode") or "paper",
            "balance": _safe_float(state.get("balance")),
            "realized_pnl": _safe_float(state.get("realized_pnl")),
            "kill_switch": bool(state.get("kill_switch")),
            "is_paused": bool(state.get("is_paused")),
            "open_positions": len(open_positions),
        },
        "last_cycle": {
            "cycle_id": last_cycle.get("cycle_id") or "-",
            "ts": last_cycle.get("ts") or "-",
            "orders": _safe_int(last_cycle.get("orders")),
            "signals": _safe_int(last_cycle.get("signals")),
            "no_signal": _safe_int(last_cycle.get("no_signal")),
            "errors": _safe_int(last_cycle.get("errors")),
            "open_positions": _safe_int(last_cycle.get("open_positions")),
            "scanned": _safe_int(last_cycle.get("scanned")),
        },
        "window": {
            "cycles_completed": len(completed_cycles),
            "order_events": order_event_count,
            "signals": sum(_safe_int(e.get("signals")) for e in completed_cycles),
            "orders": sum(_safe_int(e.get("orders")) for e in completed_cycles),
            "errors": sum(_safe_int(e.get("errors")) for e in completed_cycles),
            "no_signal": sum(_safe_int(e.get("no_signal")) for e in completed_cycles),
        },
        "latest_market": {
            "event_type": _event_type(last_market) or "-",
            "symbol": last_market.get("symbol") or last_asset.get("symbol") or "-",
            "exchange_id": last_market.get("exchange_id") or "-",
            "rows_returned": _safe_int(last_market.get("rows_returned")),
            "last_price": _safe_float(last_asset.get("last_price")),
            "candle_ts": last_asset.get("candle_ts") or "-",
        },
        "latest_signal": {
            "event_type": _event_type(signal_source) or "-",
            "verdict": signal_source.get("final_verdict") or signal_source.get("verdict") or "-",
            "intended_side": signal_source.get("intended_side") or "-",
            "dominant_filter": signal_source.get("dominant_filter") or signal_source.get("diagnostic_filter") or "-",
            "reason": signal_source.get("diagnostic_reason") or "-",
            "technical_score": _safe_float(signal_source.get("technical_score") or signal_source.get("score")),
            "setup_quality": _safe_float(signal_source.get("setup_quality")),
            "ai_prob": _safe_float(signal_source.get("ai_prob")),
            "scenario": last_no_signal.get("scenario") or "-",
            "scenario_recommendation": last_no_signal.get("scenario_recommendation") or "-",
        },
        "latest_lsr_v2": {
            "candidate_ready": bool(last_lsr.get("candidate_ready")),
            "candidate_fresh_for_submit": bool(last_lsr.get("candidate_fresh_for_submit")),
            "candidate_age_bars": _safe_int(last_lsr.get("candidate_age_bars")),
            "max_submit_candidate_age_bars": _safe_int(last_lsr.get("max_submit_candidate_age_bars")),
            "blocked_reason": last_lsr.get("blocked_reason") or "-",
            "bridge_blocked_reason": last_lsr_bridge.get("blocked_reason") or "-",
            "side": last_lsr.get("side") or "-",
            "entry_price": _safe_float((last_lsr.get("levels") or {}).get("entry_price")) if isinstance(last_lsr.get("levels"), dict) else 0.0,
            "candidate_id": last_lsr.get("candidate_id") or "-",
        },
        "latest_guarded_bridge": {
            "blocked_reason": last_guarded.get("blocked_reason") or last_guarded.get("primary_reject_reason") or "-",
            "side": last_guarded.get("side") or "-",
            "map_score": _safe_float(last_guarded.get("map_score")),
            "runtime_structure_state": last_guarded.get("runtime_structure_state") or "-",
            "paper_orders_enabled": bool(last_guarded.get("paper_orders_enabled")),
        },
        "top_reasons": {
            "signal_filters": _top(signal_filters),
            "no_signal_reasons": _top(no_signal_reasons, 5),
            "lsr_v2_blockers": _top(lsr_reasons),
            "guarded_bridge_blockers": _top(guarded_reasons),
            "paper_unlock_reasons": _top(unlock_reasons),
        },
    }
    report["conclusion"] = _conclusion(report)
    return report


def _conclusion(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    state = report["state"]
    engine = report["engine"]
    last_cycle = report["last_cycle"]
    latest_lsr = report["latest_lsr_v2"]
    latest_signal = report["latest_signal"]
    window = report["window"]

    if state["open_positions"] > 0:
        lines.append("C'e una posizione paper aperta: controlla lo stato/Telegram, non serve aspettarsi un nuovo ingresso finche max_positions resta a 1.")
    if state["kill_switch"] or state["is_paused"]:
        lines.append("Il paper engine risulta pausato o in kill switch: prima va riarmato in paper-only.")
    if engine["state"] == "STOPPED":
        if engine["max_cycles_reached"]:
            lines.append(f"Il run e terminato per max_cycles={engine['max_cycles']}; per tenerlo acceso usa max-cycles 0 oppure rilancia una nuova finestra da 8 ore.")
        else:
            lines.append("L'ultimo evento indica engine fermo: per avere nuovi ordini il bot va rilanciato.")
    if last_cycle["errors"] > 0 or window["errors"] > 0:
        lines.append("Ci sono errori nei cicli recenti: prima va letto il log terminale/eventi.")
    if latest_lsr["candidate_ready"] and not latest_lsr["candidate_fresh_for_submit"]:
        lines.append(
            "LSR-v2 vede un candidate valido ma vecchio: anti-stale blocca l'invio finche non compare un candidate fresco."
        )
    if latest_signal["verdict"] == "HOLD":
        reason = latest_signal["reason"]
        if reason and reason != "-":
            lines.append(f"La strategia principale e in HOLD: {reason}.")
        else:
            lines.append("La strategia principale e in HOLD: nessun setup operativo fresco.")
    if window["orders"] == 0 and window["order_events"] == 0 and not lines:
        lines.append("Non risultano ordini nella finestra letta: al momento non c'e evidenza di setup eseguibile.")
    if not lines:
        lines.append("Nessun blocco evidente nella finestra letta; se non apre ancora, aumenta --tail e controlla il terminale live.")
    return lines


def format_report(report: dict[str, Any]) -> str:
    engine = report["engine"]
    state = report["state"]
    cycle = report["last_cycle"]
    window = report["window"]
    market = report["latest_market"]
    signal = report["latest_signal"]
    lsr = report["latest_lsr_v2"]
    guarded = report["latest_guarded_bridge"]

    lines = [
        "PAPER BLOCKER REPORT",
        f"engine_state={engine['state']} latest_event={engine['latest_event_type']} latest_ts={engine['latest_ts']}",
        f"mode={state['mode']} balance={state['balance']:.2f} realized_pnl={state['realized_pnl']:+.2f}",
        f"open_positions={state['open_positions']} kill_switch={state['kill_switch']} is_paused={state['is_paused']}",
        "",
        "last_cycle:",
        (
            f"  cycle_id={cycle['cycle_id']} ts={cycle['ts']} scanned={cycle['scanned']} "
            f"signals={cycle['signals']} orders={cycle['orders']} no_signal={cycle['no_signal']} errors={cycle['errors']}"
        ),
        "",
        "window:",
        (
            f"  cycles={window['cycles_completed']} signals={window['signals']} orders={window['orders']} "
            f"order_events={window['order_events']} no_signal={window['no_signal']} errors={window['errors']}"
        ),
        "",
        "market:",
        (
            f"  {market['event_type']} {market['symbol']} exchange={market['exchange_id']} "
            f"rows={market['rows_returned']} last_price={market['last_price']:.2f} candle_ts={market['candle_ts']}"
        ),
        "",
        "strategy:",
        (
            f"  verdict={signal['verdict']} intended_side={signal['intended_side']} "
            f"filter={signal['dominant_filter']} tech_score={signal['technical_score']:.2f} "
            f"setup_quality={signal['setup_quality']:.2f} ai_prob={signal['ai_prob']:.2f}"
        ),
        f"  reason={signal['reason']}",
        f"  scenario={signal['scenario']} recommendation={signal['scenario_recommendation']}",
        "",
        "lsr_v2:",
        (
            f"  ready={lsr['candidate_ready']} fresh={lsr['candidate_fresh_for_submit']} "
            f"age_bars={lsr['candidate_age_bars']} max_age_bars={lsr['max_submit_candidate_age_bars']} "
            f"side={lsr['side']} entry={lsr['entry_price']:.2f}"
        ),
        f"  blocked_reason={lsr['blocked_reason']} bridge_blocked_reason={lsr['bridge_blocked_reason']}",
        f"  candidate_id={lsr['candidate_id']}",
        "",
        "guarded_bridge:",
        (
            f"  blocked_reason={guarded['blocked_reason']} side={guarded['side']} "
            f"map_score={guarded['map_score']:.2f} structure={guarded['runtime_structure_state']} "
            f"paper_orders_enabled={guarded['paper_orders_enabled']}"
        ),
        "",
        "top_reasons:",
    ]
    for group, rows in report["top_reasons"].items():
        label = "  " + group + ":"
        lines.append(label)
        if rows:
            for row in rows:
                lines.append(f"    {row['reason']}: {row['count']}")
        else:
            lines.append("    -")
    lines.append("")
    lines.append("conclusion:")
    for item in report["conclusion"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain why paper-live did not open orders in recent cycles.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tail", type=int, default=2000, help="How many recent JSONL events to inspect.")
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
