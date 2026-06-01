"""Prompt 29.4.4t-17 — LSR-v2 fourth supervised paper-only submit execution scaffold.

Fail-closed execution scaffold for a future fourth LSR-v2 paper trade.  The
module consumes the validated submit preflight and safety artifacts, then
reports whether a paper submit execution would be possible.  In the current
no-candidate/no-order-intent state it must PASS as a no-order diagnostic.

It never submits when there is no validated paper_order_intent, never invents
an order, never opens/closes positions, never touches live/testnet/exchange
brokers, never starts a scheduler, never sends Telegram traffic, and never
mutates paper_state or paper_status unless a future explicit execution path is
implemented and armed by a separate patch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import argparse
import json
import os

PROMPT_ID = "29.4.4t-17"
EVENT_TYPE = "LSR_V2_FOURTH_TRADE_SUBMIT_EXECUTION"
REPORT_NAME = "lsr_v2_fourth_trade_submit_execution_report.json"
JSONL_NAME = "lsr_v2_fourth_trade_submit_execution.jsonl"

T16_REPORT_NAME = "lsr_v2_fourth_trade_submit_preflight_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

T16_PASS_DECISION = "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"
PASS_DECISION = "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_SUBMIT_EXECUTION_PREFLIGHT_NOT_READY"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_SUBMIT_EXECUTION_SOURCE_MARKERS_MISSING"
STATE_NOT_FLAT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_SUBMIT_EXECUTION_STATE_NOT_FLAT"
ENV_INVALID_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_SUBMIT_EXECUTION_OPERATOR_ENV_INVALID"
FAILED_DECISION = "REJECT_LSR_V2_FOURTH_SUBMIT_EXECUTION_SAFETY_FAILED"

ENABLE_ENV = "LSR_V2_FOURTH_TRADE_REARM_ENABLE"
CONFIRM_ENV = "LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION"
MAX_POSITIONS_ENV = "LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS"
CONFIRM_PHRASE = "I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY"

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/core/lsr_v2_fourth_trade_submit_preflight.py": (
        "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT",
        "paper_order_intent_ready",
        "would_submit",
    ),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "ready", "pass", "open"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null", "closed"}:
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
        if out in {float("inf"), float("-inf")}:
            return default
        return out
    except Exception:
        return default


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _row_status(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_open_position(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "OPEN")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("open"), True)


def _is_pending_order(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "")
    if status in {"", "CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED", "FILLED"}:
        return False
    return _safe_bool(row.get("pending"), True)


def _pass_report(report: Mapping[str, Any], decision: str) -> bool:
    return report.get("status") == "PASS" and report.get("decision") == decision


def _source_marker_audit(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    missing_files: list[str] = []
    missing_markers: dict[str, list[str]] = {}
    for rel, markers in _SOURCE_MARKERS.items():
        path = root / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        miss = [marker for marker in markers if marker not in text]
        if miss:
            missing_markers[rel] = miss
    return {
        "submit_execution_source_files_present": not missing_files,
        "submit_execution_required_markers_present": not missing_files and not missing_markers,
        "missing_submit_execution_source_files": missing_files,
        "missing_submit_execution_source_markers": missing_markers,
    }


def _operator_controls(env_map: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env_map if env_map is not None else os.environ
    enable_value = str(source.get(ENABLE_ENV, "")).strip()
    confirm_value = str(source.get(CONFIRM_ENV, "")).strip()
    max_pos_value = str(source.get(MAX_POSITIONS_ENV, "")).strip()

    active_keys = []
    for key in (ENABLE_ENV, CONFIRM_ENV, MAX_POSITIONS_ENV):
        if str(source.get(key, "")).strip() not in {"", "0", "false", "False", "no", "NO", "off", "OFF"}:
            active_keys.append(key)

    enable_ok = enable_value == "1"
    confirmation_ok = confirm_value == CONFIRM_PHRASE
    max_positions = _safe_int(max_pos_value, 0)
    max_positions_ok = max_positions == 1
    controls_valid = enable_ok and confirmation_ok and max_positions_ok
    return {
        "active_lsr_v2_operator_env_count": len(active_keys),
        "active_lsr_v2_operator_env_keys": sorted(active_keys),
        "operator_env_absent": len(active_keys) == 0,
        "submit_execution_operator_env_currently_active": bool(active_keys),
        "submit_execution_enable_env_name": ENABLE_ENV,
        "submit_execution_enable_env_value": enable_value,
        "submit_execution_enable_ok": enable_ok,
        "submit_execution_confirmation_env_name": CONFIRM_ENV,
        "submit_execution_confirmation_env_value_present": bool(confirm_value),
        "submit_execution_confirmation_ok": confirmation_ok,
        "submit_execution_confirmation_phrase": CONFIRM_PHRASE,
        "submit_execution_max_positions_env_name": MAX_POSITIONS_ENV,
        "submit_execution_max_positions_env_value": max_pos_value,
        "submit_execution_max_positions": max_positions if max_positions else 1,
        "submit_execution_max_positions_ok": max_positions_ok,
        "submit_execution_operator_controls_valid": controls_valid,
    }


def _state_status_snapshot(paper_state: Mapping[str, Any], paper_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(paper_state.get("positions"), id_field="position_id")
    orders = _collection_rows(paper_state.get("orders"), id_field="order_id")
    open_positions = [row for row in positions if _is_open_position(row)]
    pending_orders = [row for row in orders if _is_pending_order(row)]
    status_open = _safe_int(paper_status.get("open_positions"), len(open_positions))
    status_pending = _safe_int(paper_status.get("pending_orders"), len(pending_orders))
    return {
        "open_positions_after": len(open_positions),
        "open_lsr_v2_positions_after": 0,
        "pending_orders_after": len(pending_orders),
        "pending_lsr_v2_orders_after": 0,
        "paper_status_open_positions_after": status_open,
        "paper_status_pending_orders_after": status_pending,
        "pending_orders_clear": len(pending_orders) == 0 and status_pending == 0,
        "flat_state_confirmed": len(open_positions) == 0 and status_open == 0,
        "paper_state_status_consistency": len(open_positions) == status_open and len(pending_orders) == status_pending,
        "balance_after": _safe_float(paper_state.get("balance") or paper_status.get("balance"), 0.0),
        "realized_pnl_after": _safe_float(paper_state.get("realized_pnl") or paper_status.get("realized_pnl"), 0.0),
    }


def _submit_execution_model(preflight: Mapping[str, Any], controls: Mapping[str, Any]) -> dict[str, Any]:
    paper_order_intent = preflight.get("paper_order_intent") if isinstance(preflight.get("paper_order_intent"), Mapping) else {}
    paper_order_intent_ready = _safe_bool(preflight.get("paper_order_intent_ready"), False) and bool(paper_order_intent)
    route_candidate_available = _safe_bool(preflight.get("route_candidate_available"), False)
    would_route = _safe_bool(preflight.get("would_route"), False)
    would_create_order = _safe_bool(preflight.get("would_create_order"), False)
    preflight_would_submit = _safe_bool(preflight.get("would_submit"), False)
    controls_valid = _safe_bool(controls.get("submit_execution_operator_controls_valid"), False)

    if not _safe_bool(preflight.get("submit_preflight_ready"), False):
        reason = "submit_preflight_not_ready"
    elif not route_candidate_available:
        reason = "no_route_candidate_available"
    elif not would_route:
        reason = "would_route_false"
    elif not would_create_order or not paper_order_intent_ready:
        reason = "no_paper_order_intent_available"
    elif not controls_valid:
        reason = "operator_controls_not_valid"
    else:
        reason = "explicit_submit_execution_patch_required"

    return {
        "route_candidate_available": route_candidate_available,
        "would_route": would_route,
        "would_create_order": would_create_order,
        "would_create_order_count": 1 if would_create_order else 0,
        "paper_order_intent": dict(paper_order_intent),
        "paper_order_intent_ready": paper_order_intent_ready,
        "submit_preflight_would_submit": preflight_would_submit,
        "submit_execution_scaffold_ready": True,
        "submit_execution_would_validate_order_intent": paper_order_intent_ready,
        "submit_execution_would_submit_if_execution_patch_enabled": bool(paper_order_intent_ready and controls_valid),
        "submit_execution_blocked_reason": reason,
        "submit_execution_diagnostic": "NO_ORDER_SUBMIT_EXECUTION_DIAGNOSTIC" if not paper_order_intent_ready else "ORDER_INTENT_PRESENT_EXECUTION_STILL_BLOCKED",
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "broker_close_called": False,
    }


def build_lsr_v2_fourth_trade_submit_execution_report(
    *,
    submit_preflight: Mapping[str, Any],
    paper_state: Mapping[str, Any],
    paper_status: Mapping[str, Any],
    source_audit: Mapping[str, Any] | None = None,
    env_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source_audit = dict(source_audit or {})
    controls = _operator_controls(env_map)
    state = _state_status_snapshot(paper_state, paper_status)
    model = _submit_execution_model(submit_preflight, controls)

    report_ready = _pass_report(submit_preflight, T16_PASS_DECISION) and _safe_bool(submit_preflight.get("submit_preflight_ready"), False)
    inherited_live = _safe_bool(submit_preflight.get("live_enabled"), False)
    inherited_testnet = _safe_bool(submit_preflight.get("testnet_enabled"), False)
    inherited_exchange = _safe_bool(submit_preflight.get("exchange_broker_enabled"), False)
    telegram_network_called = _safe_bool(submit_preflight.get("telegram_network_called"), False)
    telegram_send_allowed = _safe_bool(submit_preflight.get("telegram_send_allowed"), False)
    scheduler_enabled = _safe_bool(submit_preflight.get("scheduler_enabled"), False)
    scheduler_started = _safe_bool(submit_preflight.get("scheduler_started"), False)
    fourth_trade_locked = _safe_bool(submit_preflight.get("fourth_trade_locked"), True)
    stability_lock_active = _safe_bool(submit_preflight.get("stability_lock_active"), True)
    fourth_trade_allowed = _safe_bool(submit_preflight.get("fourth_trade_allowed"), False)

    blockers: list[str] = []
    if not report_ready:
        blockers.append("submit_preflight_not_ready")
    if not _safe_bool(source_audit.get("submit_execution_required_markers_present"), False):
        blockers.append("submit_execution_required_markers_missing")
    if not state["flat_state_confirmed"] or not state["pending_orders_clear"] or not state["paper_state_status_consistency"]:
        blockers.append("paper_state_or_status_not_flat")
    if not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed:
        blockers.append("fourth_trade_lock_or_stability_invalid")
    if inherited_live:
        blockers.append("live_enabled")
    if inherited_testnet:
        blockers.append("testnet_enabled")
    if inherited_exchange:
        blockers.append("exchange_broker_enabled")
    if telegram_network_called or telegram_send_allowed:
        blockers.append("telegram_network_or_send_enabled")
    if scheduler_enabled or scheduler_started:
        blockers.append("scheduler_enabled_or_started")
    if _safe_bool(model.get("paper_order_intent_ready"), False) and not _safe_bool(controls.get("submit_execution_operator_controls_valid"), False):
        blockers.append("operator_controls_not_valid_for_available_order_intent")

    hard_fail = any(key in blockers for key in ("live_enabled", "testnet_enabled", "exchange_broker_enabled"))
    if hard_fail:
        status = "FAIL"; decision = FAILED_DECISION
    elif "operator_controls_not_valid_for_available_order_intent" in blockers:
        status = "WARN"; decision = ENV_INVALID_DECISION
    elif "submit_execution_required_markers_missing" in blockers:
        status = "WARN"; decision = SOURCE_MARKERS_MISSING_DECISION
    elif "paper_state_or_status_not_flat" in blockers or "fourth_trade_lock_or_stability_invalid" in blockers:
        status = "WARN"; decision = STATE_NOT_FLAT_DECISION
    elif "submit_preflight_not_ready" in blockers:
        status = "WARN"; decision = REPORTS_NOT_READY_DECISION
    elif blockers:
        status = "FAIL"; decision = FAILED_DECISION
    else:
        status = "PASS"; decision = PASS_DECISION

    submit_execution_ready = status == "PASS"
    no_order = not _safe_bool(model.get("paper_order_intent_ready"), False)

    return {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "FOURTH_TRADE_SUBMIT_EXECUTION_SCAFFOLD",
            "SUPERVISED_PAPER_ONLY",
            "FAIL_CLOSED",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT_WITHOUT_ORDER_INTENT",
            "NO_BROKER_CALL",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["NO_ORDER_EXECUTION_DIAGNOSTIC"] if no_order else ["ORDER_INTENT_PRESENT_EXECUTION_STILL_REQUIRES_EXPLICIT_PATCH"]),
        "submit_execution_ready": submit_execution_ready,
        "candidate_submit_execution_scaffold_ready": submit_execution_ready,
        "candidate_submit_execution_allowed": False,
        "candidate_routing_execution_allowed": False,
        "candidate_detection_allowed": False,
        "future_candidate_detection_allowed": False,
        "fourth_trade_rearm_allowed": False,
        "fourth_trade_allowed": False,
        "future_fourth_trade_unlock_allowed": False,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "live_enabled": inherited_live,
        "testnet_enabled": inherited_testnet,
        "exchange_broker_enabled": inherited_exchange,
        "telegram_network_called": telegram_network_called,
        "telegram_send_allowed": telegram_send_allowed,
        "scheduler_enabled": scheduler_enabled,
        "scheduler_started": scheduler_started,
        **state,
        **source_audit,
        **controls,
        **model,
        "submit_preflight_ready": report_ready,
        "route_preflight_ready": _safe_bool(submit_preflight.get("route_preflight_ready"), False),
        "handoff_dry_run_ready": _safe_bool(submit_preflight.get("handoff_dry_run_ready"), False),
        "submit_execution_operator_env_currently_active": _safe_bool(controls.get("submit_execution_operator_env_currently_active"), False),
        "broker_submit_called_by_submit_execution": False,
        "broker_close_called_by_submit_execution": False,
        "orders_submitted_by_submit_execution": 0,
        "positions_opened_by_submit_execution": 0,
        "positions_closed_by_submit_execution": 0,
        "paper_state_modified_by_submit_execution": False,
        "paper_status_modified_by_submit_execution": False,
        "submit_execution_events_total": _safe_int(submit_preflight.get("submit_execution_events_total") or 3, 3),
        "close_execution_events_total": _safe_int(submit_preflight.get("close_execution_events_total") or 3, 3),
        "aggregate_realized_pnl": _safe_float(submit_preflight.get("aggregate_realized_pnl"), 0.0),
        "balance_after": _safe_float(state.get("balance_after") or submit_preflight.get("balance_after"), 0.0),
        "realized_pnl_after": _safe_float(state.get("realized_pnl_after"), 0.0),
        "lifecycle_state": str(submit_preflight.get("lifecycle_state") or ""),
        "dashboard_mode": str(submit_preflight.get("dashboard_mode") or ""),
        "visual_sl_tp_progress_bar_ready": _safe_bool(submit_preflight.get("visual_sl_tp_progress_bar_ready"), False),
        "visual_sl_tp_progress_bar": str(submit_preflight.get("visual_sl_tp_progress_bar") or ""),
        "telegram_payload_ready": _safe_bool(submit_preflight.get("telegram_payload_ready"), False),
        "telegram_update_ready": _safe_bool(submit_preflight.get("telegram_update_ready"), False),
        "blocked_until_real_route_candidate_and_explicit_execution_patch": [
            "fourth_specific_route_candidate",
            "paper_order_intent_ready",
            "candidate_submit_execution",
            "broker_submit",
            "telegram_network_send",
            "scheduler_start",
            "paper_engine_candidate_execution_hook",
        ],
        "next_step": "validate_submit_execution_scaffold_then_wait_for_fourth_candidate_or_generic_cycle_refactor",
        "recommended_next_patch": "wait_for_fourth_specific_candidate_or_prepare_generic_LSR_v2_paper_cycle_refactor",
    }


def build_lsr_v2_fourth_trade_submit_execution_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(data_dir)
    submit_preflight = _read_json(root / T16_REPORT_NAME)
    paper_state = _read_json(root / PAPER_STATE_NAME)
    paper_status = _read_json(root / PAPER_STATUS_NAME)
    source_audit = _source_marker_audit(project_root)
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=submit_preflight,
        paper_state=paper_state,
        paper_status=paper_status,
        source_audit=source_audit,
    )
    report["settings"] = {
        "data_dir": str(root),
        "project_root": str(project_root),
        "report_name": REPORT_NAME,
        "jsonl_name": JSONL_NAME,
        "fail_closed": True,
        "scaffold_only": True,
    }
    report["report"] = str(root / REPORT_NAME)
    report["jsonl"] = str(root / JSONL_NAME)
    if write_report:
        _write_json(root / REPORT_NAME, report)
        _append_jsonl(root / JSONL_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PROMPT_ID)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    report = build_lsr_v2_fourth_trade_submit_execution_report_from_files(
        data_dir=args.data_dir,
        project_root=args.project_root,
        write_report=not args.no_write,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
