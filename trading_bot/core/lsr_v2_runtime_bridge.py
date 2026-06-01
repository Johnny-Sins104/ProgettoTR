"""Prompt 29.4.4s-10f-1 — LSR-v2 runtime/operator route cycle-scope audit.

This module evaluates the approved LSR-v2 research profile inside a paper
runtime cycle, but only as audit telemetry.  It emits cycle-scoped candidate and
bridge diagnostics and force-pins every execution path to fail-closed values:
no routing, no broker call, no paper order submission, and no position opening.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import json

try:  # package imports in full project
    from .liquidity_sweep_reversal_v2 import LSRV2Settings, detect_lsr_v2_candidates, normalize_timeframe_label
    from .lsr_v2_paper_supervised_bridge import (
        EVENT_TYPE as BRIDGE_EVENT_TYPE,
        LSRV2PaperSupervisedBridgeSettings,
        build_lsr_v2_paper_supervised_bridge_event,
        promotion_gate_passed,
    )
    from .lsr_v2_promotion_gate import REPORT_NAME as PROMOTION_GATE_REPORT_NAME
except Exception:  # pragma: no cover - script-style fallback
    from liquidity_sweep_reversal_v2 import LSRV2Settings, detect_lsr_v2_candidates, normalize_timeframe_label  # type: ignore
    from lsr_v2_paper_supervised_bridge import (  # type: ignore
        EVENT_TYPE as BRIDGE_EVENT_TYPE,
        LSRV2PaperSupervisedBridgeSettings,
        build_lsr_v2_paper_supervised_bridge_event,
        promotion_gate_passed,
    )
    from lsr_v2_promotion_gate import REPORT_NAME as PROMOTION_GATE_REPORT_NAME  # type: ignore

PROMPT_ID = "29.4.4s-10f-1"
RUNTIME_CANDIDATE_EVENT_TYPE = "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
RUNTIME_BRIDGE_EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
RUNTIME_REPORT_NAME = "lsr_v2_runtime_bridge_report.json"
RUNTIME_JSONL_NAME = "lsr_v2_runtime_bridge_audit.jsonl"
OPERATOR_ROUTE_REPORT_NAME = "lsr_v2_operator_route_audit_report.json"
OPERATOR_ROUTE_JSONL_NAME = "lsr_v2_operator_route_audit.jsonl"
STANDALONE_REPORT_NAME = "lsr_v2_paper_supervised_bridge_report.json"

READY_DECISION = "LSR_V2_RUNTIME_CYCLE_BRIDGE_READY_DIAGNOSTIC"
NO_CANDIDATES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RUNTIME_BRIDGE_NO_CANDIDATES"
PROMOTION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_GATE_MISSING"
FAIL_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RUNTIME_BRIDGE_FAIL_CLOSED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RUNTIME_BRIDGE_ERROR"
OPERATOR_ROUTE_READY_DECISION = "LSR_V2_OPERATOR_ROUTE_AUDIT_READY_DIAGNOSTIC"
OPERATOR_ROUTE_NO_ROUTE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_ROUTE_NO_WOULD_ROUTE"
OPERATOR_ROUTE_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_ROUTE_NO_EVENTS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


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


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"_non_object_json": payload}
    except Exception as exc:
        return {"_read_error": str(exc)}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _runtime_event_key(event: Mapping[str, Any]) -> str:
    """Stable key for de-duplicating diagnostic runtime events.

    Incremental paper-cycle artifact writes can see the same in-memory event list
    multiple times.  The event payload itself is immutable enough for exact JSON
    de-duplication, and using a compact semantic fallback keeps malformed rows
    from inflating route counts.
    """
    try:
        return json.dumps(dict(event), sort_keys=True, default=str)
    except Exception:
        return "|".join([
            str(event.get("event_type") or ""),
            str(event.get("cycle_id") or ""),
            str(event.get("symbol") or ""),
            str(event.get("candidate_id") or ""),
            str(event.get("created_at") or event.get("ts") or ""),
        ])


def _dedupe_runtime_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        key = _runtime_event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _filter_runtime_events_for_cycle(events: Iterable[Mapping[str, Any]], cycle_id: str | None) -> list[dict[str, Any]]:
    allowed = {RUNTIME_CANDIDATE_EVENT_TYPE, BRIDGE_EVENT_TYPE}
    selected: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("event_type")
        if event_type not in allowed:
            continue
        if cycle_id and str(event.get("cycle_id") or "") != str(cycle_id):
            continue
        selected.append(dict(event))
    return _dedupe_runtime_events(selected)


def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _nested_get(mapping: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


@dataclass(frozen=True)
class LSRV2RuntimeBridgeSettings:
    enabled: bool = True
    emit_runtime_events: bool = True
    fail_closed: bool = True
    data_dir: str = "data"
    events_name: str = "paper_events.jsonl"
    runtime_report_name: str = RUNTIME_REPORT_NAME
    runtime_jsonl_name: str = RUNTIME_JSONL_NAME
    operator_route_report_name: str = OPERATOR_ROUTE_REPORT_NAME
    operator_route_jsonl_name: str = OPERATOR_ROUTE_JSONL_NAME
    promotion_gate_report_name: str = PROMOTION_GATE_REPORT_NAME
    standalone_bridge_report_name: str = STANDALONE_REPORT_NAME
    timeframe: str = "5m"
    max_scan_rows: int = 500
    max_recent_candidate_bars: int = 12
    max_event_lines: int = 50000
    require_candidate_ready: bool = True
    profile_name: str = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    selected_overlay_id: str = "combo_loss3_dd10_side_cap"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dataframe_to_ohlcv_rows(df: Any, *, symbol: str, max_rows: int = 500) -> list[dict[str, Any]]:
    """Convert a pandas-like OHLCV dataframe to detector rows.

    The project runtime uses capitalized columns (Open/High/Low/Close/Volume);
    the LSR-v2 detector accepts lowercase aliases.  This helper keeps the bridge
    independent from pandas at import time by using duck typing.
    """
    if df is None:
        return []
    try:
        total = int(getattr(df, "shape", [0])[0] or 0)
    except Exception:
        total = 0
    if total <= 0:
        return []
    try:
        view = df.tail(max(1, int(max_rows))) if hasattr(df, "tail") else df
        records = view.to_dict("records") if hasattr(view, "to_dict") else []
        index_values = list(getattr(view, "index", []))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            continue
        ts = index_values[idx] if idx < len(index_values) else idx
        row = dict(raw)
        out.append({
            "timestamp": row.get("timestamp") or row.get("Datetime") or row.get("Date") or str(ts),
            "symbol": symbol,
            "open": row.get("open", row.get("Open", row.get("o"))),
            "high": row.get("high", row.get("High", row.get("h"))),
            "low": row.get("low", row.get("Low", row.get("l"))),
            "close": row.get("close", row.get("Close", row.get("c"))),
            "volume": row.get("volume", row.get("Volume", row.get("vol", row.get("base_volume", 0.0)))),
            "market_regime": row.get("market_regime", row.get("regime", "RUNTIME")),
        })
    return out


def _candidate_ready(candidate: Mapping[str, Any], settings: LSRV2RuntimeBridgeSettings) -> bool:
    ready = _safe_bool(candidate.get("candidate_ready"), False)
    if settings.require_candidate_ready and not ready:
        return False
    lifecycle = candidate.get("lifecycle") if isinstance(candidate.get("lifecycle"), Mapping) else {}
    if not _safe_bool(lifecycle.get("retest_ready"), False):
        return False
    quality_grade = str(_nested_get(candidate, "quality", "grade", default="") or "")
    if quality_grade not in {"A", "QUALITY_A", ""}:
        return False
    return True


def _select_runtime_candidate(candidates: list[dict[str, Any]], *, row_count: int, settings: LSRV2RuntimeBridgeSettings) -> dict[str, Any] | None:
    if not candidates:
        return None
    recent_candidates: list[dict[str, Any]] = []
    min_index = max(0, int(row_count) - max(1, int(settings.max_recent_candidate_bars)))
    for candidate in candidates:
        retest_i = _safe_int(candidate.get("retest_index"), -1)
        reclaim_i = _safe_int(candidate.get("reclaim_index"), -1)
        recent_i = max(retest_i, reclaim_i)
        if recent_i >= min_index:
            recent_candidates.append(candidate)
    pool = recent_candidates if recent_candidates else candidates
    ready = [c for c in pool if _candidate_ready(c, settings)]
    if ready:
        return ready[-1]
    return pool[-1]


def build_lsr_v2_runtime_candidate_audit_event(
    *,
    cycle_id: str,
    symbol: str,
    timeframe: str,
    rows: list[dict[str, Any]],
    candidate: Mapping[str, Any] | None,
    detected_candidates: int,
    settings: LSRV2RuntimeBridgeSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2RuntimeBridgeSettings(timeframe=timeframe)
    cand = dict(candidate or {})
    lifecycle = cand.get("lifecycle") if isinstance(cand.get("lifecycle"), Mapping) else {}
    levels = cand.get("levels") if isinstance(cand.get("levels"), Mapping) else {}
    risk = cand.get("risk") if isinstance(cand.get("risk"), Mapping) else {}
    quality = cand.get("quality") if isinstance(cand.get("quality"), Mapping) else {}
    candidate_ready = _candidate_ready(cand, settings) if cand else False
    retest_ready = _safe_bool(lifecycle.get("retest_ready"), False)
    blocked_reasons: list[str] = []
    if not settings.enabled:
        blocked_reasons.append("lsr_v2_runtime_bridge_disabled")
    if not cand:
        blocked_reasons.append("no_lsr_v2_runtime_candidate")
    elif not candidate_ready:
        blocked_reasons.append("lsr_v2_runtime_candidate_not_ready")
    if not rows:
        blocked_reasons.append("no_runtime_market_rows")
    if not settings.fail_closed:
        blocked_reasons.append("fail_closed_setting_disabled")
    return {
        "event_type": RUNTIME_CANDIDATE_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(cycle_id or ""),
        "symbol": str(symbol or cand.get("symbol") or ""),
        "timeframe": normalize_timeframe_label(timeframe or cand.get("timeframe") or settings.timeframe),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "input_rows": len(rows),
        "detected_candidates": int(detected_candidates),
        "candidate_id": str(cand.get("candidate_id") or ""),
        "candidate_source_event_type": str(cand.get("event_type") or ""),
        "candidate_ready": bool(candidate_ready),
        "retest_ready": bool(retest_ready),
        "lifecycle": {
            "liquidity_pool_detected": _safe_bool(lifecycle.get("liquidity_pool_detected"), bool(cand)),
            "sweep_detected": _safe_bool(lifecycle.get("sweep_detected"), bool(cand)),
            "failed_continuation": _safe_bool(lifecycle.get("failed_continuation"), bool(cand)),
            "structure_reclaim": _safe_bool(lifecycle.get("structure_reclaim"), bool(cand)),
            "choch_bos_approx": _safe_bool(lifecycle.get("choch_bos_approx"), bool(cand)),
            "retest_ready": bool(retest_ready),
        },
        "side": str(cand.get("side") or "").upper(),
        "sweep_timestamp": cand.get("sweep_timestamp"),
        "reclaim_timestamp": cand.get("reclaim_timestamp"),
        "retest_timestamp": cand.get("retest_timestamp"),
        "sweep_index": cand.get("sweep_index"),
        "reclaim_index": cand.get("reclaim_index"),
        "retest_index": cand.get("retest_index"),
        "levels": {
            "entry_price": _safe_float(levels.get("entry_price"), 0.0),
            "stop_loss": _safe_float(levels.get("stop_loss"), 0.0),
            "take_profit": _safe_float(levels.get("take_profit"), 0.0),
            "liquidity_pool_level": _safe_float(levels.get("liquidity_pool_level"), 0.0),
            "sweep_extreme": _safe_float(levels.get("sweep_extreme"), 0.0),
        },
        "risk": {
            "gross_rr": _safe_float(risk.get("gross_rr"), 0.0),
            "cost_to_r": _safe_float(risk.get("cost_to_r"), 0.0),
            "target_rr": _safe_float(risk.get("target_rr"), 0.0),
        },
        "quality": {
            "grade": quality.get("grade"),
            "score": quality.get("score"),
            "reasons": quality.get("reasons") if isinstance(quality.get("reasons"), list) else [],
        },
        "blocked_reason": blocked_reasons[0] if blocked_reasons else "runtime_candidate_ready_audit_only",
        "blocked_reasons": blocked_reasons,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "would_submit": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "audit_only": True,
    }


def build_lsr_v2_runtime_bridge_events_for_symbol(
    *,
    df: Any,
    cycle_id: str,
    symbol: str,
    timeframe: str,
    promotion_gate_report: Mapping[str, Any] | None,
    bridge_settings: LSRV2PaperSupervisedBridgeSettings | None = None,
    runtime_settings: LSRV2RuntimeBridgeSettings | None = None,
    open_positions_count: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_settings = runtime_settings or LSRV2RuntimeBridgeSettings(timeframe=timeframe)
    bridge_settings = bridge_settings or LSRV2PaperSupervisedBridgeSettings.from_config()
    rows = dataframe_to_ohlcv_rows(df, symbol=symbol, max_rows=runtime_settings.max_scan_rows)
    detector_settings = LSRV2Settings(
        symbol=symbol,
        timeframe=normalize_timeframe_label(timeframe),
        max_rows=runtime_settings.max_scan_rows,
        # Keep this consistent with the locked profile/candidate audit defaults.
        target_rr=2.0,
        require_retest_for_candidate_ready=True,
    )
    try:
        candidates = detect_lsr_v2_candidates(rows, detector_settings)
    except Exception:
        candidates = []
    candidate = _select_runtime_candidate(candidates, row_count=len(rows), settings=runtime_settings)
    candidate_event = build_lsr_v2_runtime_candidate_audit_event(
        cycle_id=cycle_id,
        symbol=symbol,
        timeframe=timeframe,
        rows=rows,
        candidate=candidate,
        detected_candidates=len(candidates),
        settings=runtime_settings,
    )
    bridge_event = build_lsr_v2_paper_supervised_bridge_event(
        settings=bridge_settings,
        promotion_gate_report=promotion_gate_report or {},
        candidate_event=candidate_event,
        cycle_id=cycle_id,
        symbol=symbol,
        mode="paper",
        open_positions_count=open_positions_count,
    )
    bridge_event.update({
        "prompt_id": PROMPT_ID,
        "runtime_cycle_scoped": True,
        "runtime_candidate_event_type": RUNTIME_CANDIDATE_EVENT_TYPE,
        "runtime_detected_candidates": len(candidates),
        "runtime_candidate_ready": bool(candidate_event.get("candidate_ready")),
        "runtime_retest_ready": bool(candidate_event.get("retest_ready")),
        "runtime_bridge_integration_prompt_id": PROMPT_ID,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "would_submit": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "audit_only": True,
    })
    if not _safe_bool(candidate_event.get("candidate_ready"), False) and "no_lsr_v2_runtime_candidate_ready" not in bridge_event.get("blocked_reasons", []):
        reasons = list(bridge_event.get("blocked_reasons") if isinstance(bridge_event.get("blocked_reasons"), list) else [])
        reasons.append("no_lsr_v2_runtime_candidate_ready")
        bridge_event["blocked_reasons"] = reasons
        if not bridge_event.get("blocked_reason") or bridge_event.get("blocked_reason") == "paper_supervised_bridge_fail_closed":
            bridge_event["blocked_reason"] = reasons[0]
    return candidate_event, bridge_event


def summarize_lsr_v2_runtime_bridge_events(
    *,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2RuntimeBridgeSettings | None = None,
    standalone_report: Mapping[str, Any] | None = None,
    promotion_gate_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2RuntimeBridgeSettings()
    rows = _filter_runtime_events_for_cycle((dict(e) for e in events), cycle_id)
    candidate_events = [e for e in rows if e.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE]
    bridge_events = [e for e in rows if e.get("event_type") == BRIDGE_EVENT_TYPE]
    candidate_ready_events = [e for e in candidate_events if _safe_bool(e.get("candidate_ready"), False)]
    would_route_events = [e for e in bridge_events if _safe_bool(e.get("would_route"), False)]
    would_submit_events = [e for e in bridge_events if _safe_bool(e.get("would_submit"), False)]
    operator_enable = any(_safe_bool(e.get("operator_enable"), False) for e in bridge_events)
    operator_confirmation_ok = any(_safe_bool(e.get("operator_confirmation_ok"), False) for e in bridge_events)
    operator_authorized = any(_safe_bool(e.get("operator_authorized"), False) for e in bridge_events)
    promotion = dict(promotion_gate_report or {})
    if not promotion:
        promotion = _read_json(Path(data_dir) / settings.promotion_gate_report_name)
    promotion_ok = promotion_gate_passed(promotion)
    standalone = dict(standalone_report or {})
    if not standalone:
        standalone = _read_json(Path(data_dir) / settings.standalone_bridge_report_name)
    standalone_cycle_id = str(standalone.get("latest_cycle_id") or standalone.get("cycle_id") or "")
    standalone_events = _safe_int(standalone.get("bridge_events"), 0)
    standalone_ready = _safe_int(standalone.get("candidate_ready_events"), 0)
    stale = bool(standalone and cycle_id and standalone_cycle_id and standalone_cycle_id != cycle_id)
    if standalone and cycle_id and not standalone_cycle_id:
        stale = True

    blocked_reasons: list[Any] = []
    for event in bridge_events + candidate_events:
        reasons = event.get("blocked_reasons") if isinstance(event.get("blocked_reasons"), list) else [event.get("blocked_reason")]
        blocked_reasons.extend([r for r in reasons if r])

    blockers: list[str] = []
    if not promotion:
        blockers.append("promotion_gate_missing")
    elif not promotion_ok:
        blockers.append("promotion_gate_not_pass")
    if not bridge_events:
        blockers.append("no_runtime_bridge_events")
    if would_submit_events:
        blockers.append("would_submit_true_safety_violation")
    if any(_safe_bool(e.get("broker_submit_called"), False) for e in bridge_events):
        blockers.append("broker_submit_called_safety_violation")
    if sum(_safe_int(e.get("orders_submitted_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) != 0:
        blockers.append("runtime_orders_nonzero_safety_violation")
    if sum(_safe_int(e.get("positions_opened_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) != 0:
        blockers.append("runtime_positions_nonzero_safety_violation")

    safety_checks = {
        "promotion_gate_pass": bool(promotion_ok),
        "would_submit_zero": len(would_submit_events) == 0,
        "broker_submit_called_false": not any(_safe_bool(e.get("broker_submit_called"), False) for e in bridge_events),
        "orders_submitted_zero": sum(_safe_int(e.get("orders_submitted_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) == 0,
        "positions_opened_zero": sum(_safe_int(e.get("positions_opened_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) == 0,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    if not promotion:
        decision = PROMOTION_MISSING_DECISION
        status = "WARN"
    elif not bridge_events:
        decision = NO_CANDIDATES_DECISION
        status = "WARN"
    elif safety_ok:
        decision = READY_DECISION
        status = "PASS"
    else:
        decision = FAIL_CLOSED_DECISION
        status = "WARN"

    labels = ["RUNTIME_CYCLE_SCOPED", "FAIL_CLOSED", "EXECUTION_STILL_DISABLED"]
    if candidate_ready_events:
        labels.append("RUNTIME_CANDIDATE_READY_PRESENT")
    else:
        labels.append("NO_RUNTIME_CANDIDATE_READY")
    if would_route_events:
        labels.append("OPERATOR_WOULD_ROUTE_PRESENT")
    elif operator_enable and not operator_confirmation_ok:
        labels.append("OPERATOR_CONFIRMATION_MISSING")
    elif not operator_enable:
        labels.append("OPERATOR_DISABLED")
    if stale:
        labels.append("STANDALONE_REPORT_STALE")

    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_id": str(cycle_id or ""),
        "lsr_v2_runtime_cycle_id": str(cycle_id or ""),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "promotion_gate_pass": bool(promotion_ok),
        "paper_supervised_candidate": _safe_bool(promotion.get("paper_supervised_candidate"), False),
        "runtime_candidate_events": len(candidate_events),
        "runtime_candidate_ready_events": len(candidate_ready_events),
        "runtime_bridge_events": len(bridge_events),
        "runtime_would_route_count": len(would_route_events),
        "runtime_would_submit_count": 0,
        "would_route_count": len(would_route_events),
        "would_submit_count": 0,
        "operator_enable": bool(operator_enable),
        "operator_confirmation_ok": bool(operator_confirmation_ok),
        "operator_authorized": bool(operator_authorized),
        "lsr_v2_operator_enable": bool(operator_enable),
        "lsr_v2_operator_confirmation_ok": bool(operator_confirmation_ok),
        "standalone_bridge_events": standalone_events,
        "standalone_candidate_ready_events": standalone_ready,
        "lsr_v2_bridge_report_cycle_id": standalone_cycle_id,
        "lsr_v2_bridge_report_stale": stale,
        "blocked_reason_counts": _counts(blocked_reasons),
        "safety_checks": safety_checks,
        "safety_ok": safety_ok,
        "execution_enabled": False,
        "routing_enabled": False,
        "paper_order_submission_enabled": False,
        "broker_submit_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "promotion_ready": False,
        "audit_only": True,
        "report": str(Path(data_dir) / settings.runtime_report_name),
        "runtime_jsonl": str(Path(data_dir) / settings.runtime_jsonl_name),
        "sample_runtime_bridge_events_tail": bridge_events[-10:],
    }


def summarize_lsr_v2_operator_route_audit(
    *,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2RuntimeBridgeSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize operator-controlled would-route diagnostics.

    This is intentionally submit-blocked. It can prove the approved LSR-v2
    profile reaches would_route=true under manual operator controls, but
    would_submit, broker calls, orders and positions are force-pinned to zero.
    """
    settings = settings or LSRV2RuntimeBridgeSettings(data_dir=str(data_dir))
    metadata = dict(metadata or {})
    rows = _dedupe_runtime_events(dict(e) for e in events)
    if cycle_id:
        rows = [e for e in rows if str(e.get("cycle_id") or "") == str(cycle_id)]
    bridge_events = [e for e in rows if e.get("event_type") == BRIDGE_EVENT_TYPE]
    candidate_events = [e for e in rows if e.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE]
    candidate_ready_events = [e for e in candidate_events if _safe_bool(e.get("candidate_ready"), False)]
    would_route_events = [e for e in bridge_events if _safe_bool(e.get("would_route"), False)]
    operator_enable = any(_safe_bool(e.get("operator_enable"), False) for e in bridge_events)
    operator_confirmation_ok = any(_safe_bool(e.get("operator_confirmation_ok"), False) for e in bridge_events)
    operator_authorized = any(_safe_bool(e.get("operator_authorized"), False) for e in bridge_events)
    would_submit_events = [e for e in bridge_events if _safe_bool(e.get("would_submit"), False)]
    safety_checks = {
        "would_submit_zero": len(would_submit_events) == 0,
        "broker_submit_called_false": not any(_safe_bool(e.get("broker_submit_called"), False) for e in bridge_events),
        "orders_submitted_zero": sum(_safe_int(e.get("orders_submitted_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) == 0,
        "positions_opened_zero": sum(_safe_int(e.get("positions_opened_by_lsr_v2_runtime_bridge"), 0) for e in bridge_events) == 0,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    if not bridge_events and not candidate_events:
        decision = OPERATOR_ROUTE_MISSING_DECISION
        status = "WARN"
    elif would_route_events and safety_ok:
        decision = OPERATOR_ROUTE_READY_DECISION
        status = "PASS"
    else:
        decision = OPERATOR_ROUTE_NO_ROUTE_DECISION
        status = "PASS" if safety_ok else "WARN"
    blockers: list[str] = []
    if not operator_enable:
        blockers.append("operator_disabled")
    if operator_enable and not operator_confirmation_ok:
        blockers.append("operator_confirmation_missing")
    if candidate_ready_events and operator_authorized and not would_route_events:
        blockers.append("candidate_ready_operator_authorized_but_no_would_route")
    if would_submit_events:
        blockers.append("would_submit_true_safety_violation")
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "OPERATOR_ROUTE_AUDIT",
            "SUBMIT_STILL_BLOCKED",
            "FAIL_CLOSED",
        ] + (["WOULD_ROUTE_PRESENT"] if would_route_events else ["NO_WOULD_ROUTE"]),
        "blockers": blockers,
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "runtime_events"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "runtime_jsonl_deduplicated": bool(metadata.get("runtime_jsonl_deduplicated", True)),
        "historical_lsr_v2_events": _safe_int(metadata.get("historical_lsr_v2_events"), 0),
        "historical_lsr_v2_candidate_events": _safe_int(metadata.get("historical_lsr_v2_candidate_events"), 0),
        "historical_lsr_v2_bridge_events": _safe_int(metadata.get("historical_lsr_v2_bridge_events"), 0),
        "paper_events_current_cycle": metadata.get("paper_events_current_cycle") if isinstance(metadata.get("paper_events_current_cycle"), Mapping) else {},
        "runtime_jsonl_current_cycle": metadata.get("runtime_jsonl_current_cycle") if isinstance(metadata.get("runtime_jsonl_current_cycle"), Mapping) else {},
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "operator_enable": bool(operator_enable),
        "operator_confirmation_ok": bool(operator_confirmation_ok),
        "operator_authorized": bool(operator_authorized),
        "runtime_candidate_events": len(candidate_events),
        "runtime_candidate_ready_events": len(candidate_ready_events),
        "runtime_bridge_events": len(bridge_events),
        "would_route_count": len(would_route_events),
        "would_submit_count": 0,
        "orders_submitted_by_lsr_v2_operator_route_audit": 0,
        "positions_opened_by_lsr_v2_operator_route_audit": 0,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "broker_submit_called": False,
        "execution_enabled": False,
        "routing_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "promotion_ready": False,
        "safety_checks": safety_checks,
        "safety_ok": bool(safety_ok),
        "audit_only": True,
        "report": str(Path(data_dir) / settings.operator_route_report_name),
        "jsonl": str(Path(data_dir) / settings.operator_route_jsonl_name),
    }


def write_lsr_v2_operator_route_audit_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    settings: LSRV2RuntimeBridgeSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2RuntimeBridgeSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_runtime_events(dict(e) for e in events)
    operator_events = _filter_runtime_events_for_cycle(rows, cycle_id)
    _write_json(base / settings.operator_route_report_name, summarize_lsr_v2_operator_route_audit(
        cycle_id=cycle_id,
        events=operator_events,
        data_dir=base,
        settings=settings,
        metadata=metadata,
    ))
    # Keep this report/jsonl cycle-scoped and de-duplicated even when the
    # paper engine refreshes artifacts incrementally after each symbol.
    out_path = base / settings.operator_route_jsonl_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for event in operator_events:
            fh.write(json.dumps(dict(event), sort_keys=True) + "\n")
    return _read_json(base / settings.operator_route_report_name)


def write_lsr_v2_runtime_bridge_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    settings: LSRV2RuntimeBridgeSettings | None = None,
    standalone_report: Mapping[str, Any] | None = None,
    promotion_gate_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2RuntimeBridgeSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _filter_runtime_events_for_cycle((dict(e) for e in events), cycle_id)
    if settings.emit_runtime_events:
        # s-10f-1: this file is a diagnostic mirror, not the source of truth.
        # The engine refreshes artifacts after each symbol, so appending the
        # whole in-memory cycle list would duplicate earlier symbols. Keep
        # historical cycles and replace the current cycle with a de-duplicated
        # cycle-scoped view.
        runtime_path = base / settings.runtime_jsonl_name
        historical = [
            e for e in _iter_jsonl_tail(runtime_path, max_lines=settings.max_event_lines)
            if str(e.get("cycle_id") or "") != str(cycle_id or "")
        ]
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        with runtime_path.open("w", encoding="utf-8") as fh:
            for event in _dedupe_runtime_events(historical + rows):
                fh.write(json.dumps(dict(event), sort_keys=True) + "\n")
    report = summarize_lsr_v2_runtime_bridge_events(
        cycle_id=cycle_id,
        events=rows,
        data_dir=base,
        settings=settings,
        standalone_report=standalone_report,
        promotion_gate_report=promotion_gate_report,
    )
    _write_json(base / settings.runtime_report_name, report)
    try:
        write_lsr_v2_operator_route_audit_artifacts(
            data_dir=base,
            cycle_id=cycle_id,
            events=rows,
            settings=settings,
        )
    except Exception:
        pass
    return report


def load_lsr_v2_runtime_bridge_report(data_dir: str | Path = "data", settings: LSRV2RuntimeBridgeSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2RuntimeBridgeSettings(data_dir=str(data_dir))
    report = _read_json(Path(data_dir) / settings.runtime_report_name)
    # Presentation must remain fail-closed even when the report is hostile/stale.
    report = dict(report)
    report["runtime_would_submit_count"] = 0
    report["would_submit_count"] = 0
    report["orders_submitted_by_lsr_v2_runtime_bridge"] = 0
    report["positions_opened_by_lsr_v2_runtime_bridge"] = 0
    report["broker_submit_called"] = False
    report["paper_order_submission_enabled"] = False
    report["execution_enabled"] = False
    report["routing_enabled"] = False
    report["promotion_ready"] = False
    return report
