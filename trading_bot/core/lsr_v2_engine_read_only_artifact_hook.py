"""Prompt 29.4.4t-1 — LSR-v2 engine read-only dashboard/lifecycle artifact hook.

Read-only bridge between the main PaperTradingEngine and the already validated
LSR-v2 dashboard/lifecycle artifacts. This hook deliberately does not route,
submit, close, re-arm, schedule, or send Telegram messages. It only reads the
latest validated reports, builds an engine-consumable snapshot, and writes its
own audit report/jsonl so later consolidation patches can surface the snapshot
in the paper runner/footer without touching order execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-1"
EVENT_TYPE = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK"
REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
JSONL_NAME = "lsr_v2_engine_read_only_artifact_hook.jsonl"

INTEGRATION_PREFLIGHT_REPORT_NAME = "lsr_v2_paper_engine_integration_preflight_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

INTEGRATION_PREFLIGHT_PASS_DECISION = "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"
PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
REPORTS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_ARTIFACT_HOOK_REPORTS_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_ARTIFACT_HOOK_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_ARTIFACT_HOOK_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_ENGINE_ARTIFACT_HOOK_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM",
    "EXECUTE",
    "ENABLE",
    "CONFIRMATION",
    "MAX_POSITIONS",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready", "open"}:
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
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


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


def _metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _row_status(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(
        row.get("paper_order_source")
        or row.get("paper_close_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("paper_close_source")
        or meta.get("execution_source")
        or meta.get("source")
        or meta.get("closed_by")
        or ""
    )


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join(
        [
            _row_source(row),
            str(row.get("profile_name") or meta.get("profile_name") or ""),
            str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
            str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
        ]
    ).upper()
    return "LSR_V2" in text or "LIQUIDITY_SWEEP_REVERSAL" in text


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


def _operator_env_controls() -> dict[str, Any]:
    active: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = str(key).upper()
        if not upper.startswith(LSR_V2_OPERATOR_ENV_PREFIX):
            continue
        if any(marker in upper for marker in _OPERATOR_ENV_MARKERS):
            active[upper] = str(value)
    return {
        "active_lsr_v2_operator_env_keys": sorted(active),
        "active_lsr_v2_operator_env_count": len(active),
        "operator_env_absent": len(active) == 0,
    }


def _state_status_snapshot(paper_state: Mapping[str, Any], paper_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(paper_state.get("positions"), id_field="position_id")
    orders = _collection_rows(paper_state.get("orders"), id_field="order_id")
    open_lsr_positions = [row for row in positions if _is_lsr_v2_row(row) and _is_open_position(row)]
    pending_lsr_orders = [row for row in orders if _is_lsr_v2_row(row) and _is_pending_order(row)]
    status_open = _safe_int(paper_status.get("open_positions"), len(open_lsr_positions))
    status_pending = _safe_int(paper_status.get("pending_orders"), len(pending_lsr_orders))
    return {
        "open_lsr_v2_positions_after": len(open_lsr_positions),
        "pending_lsr_v2_orders_after": len(pending_lsr_orders),
        "open_positions_after": status_open,
        "pending_orders_after": status_pending,
        "paper_status_open_positions_after": status_open,
        "paper_status_pending_orders_after": status_pending,
        "flat_state_confirmed": len(open_lsr_positions) == 0 and status_open == 0,
        "pending_orders_clear": len(pending_lsr_orders) == 0 and status_pending == 0,
        "paper_state_status_consistency": len(open_lsr_positions) == status_open and len(pending_lsr_orders) == status_pending,
        "balance_after": _safe_float(paper_state.get("balance"), _safe_float(paper_status.get("equity"), 0.0)),
        "realized_pnl_after": _safe_float(paper_state.get("realized_pnl"), 0.0),
    }


def _artifact_summary(*, lifecycle: Mapping[str, Any], dashboard: Mapping[str, Any], postmortem: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dashboard_mode": str(dashboard.get("dashboard_mode") or ""),
        "lifecycle_state": str(lifecycle.get("lifecycle_state") or ""),
        "telegram_message_key": str(dashboard.get("telegram_message_key") or lifecycle.get("telegram_message_key") or ""),
        "telegram_lifecycle_message_key": str(lifecycle.get("telegram_lifecycle_message_key") or ""),
        "telegram_payload_ready": _safe_bool(dashboard.get("telegram_payload_ready"), False),
        "telegram_update_ready": _safe_bool(lifecycle.get("telegram_update_ready"), False),
        "telegram_message_text": str(lifecycle.get("telegram_message_text") or dashboard.get("telegram_message_text") or ""),
        "visual_sl_tp_progress_bar_ready": _safe_bool(lifecycle.get("visual_sl_tp_progress_bar_ready"), _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False)),
        "visual_sl_tp_progress_bar": str(lifecycle.get("visual_sl_tp_progress_bar") or dashboard.get("visual_sl_tp_progress_bar") or ""),
        "visual_sl_tp_progress_pct": _round(lifecycle.get("visual_sl_tp_progress_pct", dashboard.get("visual_sl_tp_progress_pct", 0.0))),
        "progress_state": str(lifecycle.get("progress_state") or dashboard.get("progress_state") or ""),
        "aggregate_realized_pnl": _round(postmortem.get("aggregate_realized_pnl", lifecycle.get("aggregate_realized_pnl", 0.0))),
        "balance_after": _round(lifecycle.get("balance_after", dashboard.get("balance_after", 0.0))),
        "total_realized_r_from_final_audits": _round(postmortem.get("total_realized_r_from_final_audits", 0.0)),
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(lifecycle.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(lifecycle.get("close_execution_events_total"), 0)),
    }


@dataclass(frozen=True)
class EngineReadOnlyArtifactHookSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    fail_closed: bool = True

    @property
    def report_path(self) -> Path:
        return Path(self.data_dir) / self.report_name

    @property
    def jsonl_path(self) -> Path:
        return Path(self.data_dir) / self.jsonl_name


def build_lsr_v2_engine_read_only_artifact_hook_report_from_files(
    *,
    data_dir: str | Path = "data",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = EngineReadOnlyArtifactHookSettings(
        data_dir=str(data_dir),
        report_name=report_name,
        jsonl_name=jsonl_name,
    )
    data = Path(data_dir)
    integration = _read_json(data / INTEGRATION_PREFLIGHT_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    integration_ready = integration.get("status") == "PASS" and integration.get("decision") == INTEGRATION_PREFLIGHT_PASS_DECISION
    lifecycle_ready = lifecycle.get("status") == "PASS" and lifecycle.get("decision") == LIFECYCLE_PASS_DECISION
    dashboard_ready = dashboard.get("status") == "PASS" and dashboard.get("decision") == DASHBOARD_PASS_DECISION
    postmortem_ready = postmortem.get("status") == "PASS" and postmortem.get("decision") == POSTMORTEM_PASS_DECISION

    env = _operator_env_controls()
    snapshot = _state_status_snapshot(paper_state, paper_status)
    artifact = _artifact_summary(lifecycle=lifecycle, dashboard=dashboard, postmortem=postmortem)

    fourth_trade_locked = _safe_bool(lifecycle.get("fourth_trade_locked"), _safe_bool(postmortem.get("fourth_trade_locked"), False))
    stability_lock_active = _safe_bool(lifecycle.get("stability_lock_active"), _safe_bool(postmortem.get("stability_lock_active"), False))
    fourth_trade_allowed = _safe_bool(lifecycle.get("fourth_trade_allowed"), _safe_bool(postmortem.get("fourth_trade_allowed"), True))
    reentry_detected = _safe_bool(lifecycle.get("fourth_submit_or_reentry_detected"), _safe_bool(postmortem.get("fourth_submit_or_reentry_detected"), False))

    live_enabled = _safe_bool(lifecycle.get("live_enabled"), _safe_bool(dashboard.get("live_enabled"), _safe_bool(postmortem.get("live_enabled"), _safe_bool(paper_status.get("live_enabled"), False))))
    testnet_enabled = _safe_bool(lifecycle.get("testnet_enabled"), _safe_bool(dashboard.get("testnet_enabled"), _safe_bool(postmortem.get("testnet_enabled"), _safe_bool(paper_status.get("testnet_enabled"), False))))
    exchange_broker_enabled = _safe_bool(lifecycle.get("exchange_broker_enabled"), _safe_bool(dashboard.get("exchange_broker_enabled"), _safe_bool(postmortem.get("exchange_broker_enabled"), _safe_bool(paper_status.get("exchange_broker_enabled"), False))))
    operational_unlock_allowed = _safe_bool(lifecycle.get("operational_unlock_allowed"), _safe_bool(postmortem.get("operational_unlock_allowed"), False))
    promotion_ready = _safe_bool(lifecycle.get("promotion_ready"), _safe_bool(postmortem.get("promotion_ready"), False))

    blockers: list[str] = []
    if not integration_ready:
        blockers.append("integration_preflight_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not artifact["telegram_payload_ready"] or not artifact["telegram_update_ready"]:
        blockers.append("telegram_payload_or_update_not_ready")
    if not snapshot["flat_state_confirmed"]:
        blockers.append("paper_state_or_status_not_flat")
    if not snapshot["pending_orders_clear"]:
        blockers.append("pending_orders_not_clear")
    if not snapshot["paper_state_status_consistency"]:
        blockers.append("paper_state_status_inconsistent")
    if not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed:
        blockers.append("stability_lock_not_enforced")
    if reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if not env["operator_env_absent"]:
        blockers.append("lsr_v2_operator_env_active")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")
    if promotion_ready:
        blockers.append("promotion_ready")

    safety_failed = live_enabled or testnet_enabled or exchange_broker_enabled or operational_unlock_allowed or promotion_ready
    reports_ready = integration_ready and lifecycle_ready and dashboard_ready and postmortem_ready and artifact["telegram_payload_ready"] and artifact["telegram_update_ready"]
    state_locked = snapshot["flat_state_confirmed"] and snapshot["pending_orders_clear"] and snapshot["paper_state_status_consistency"] and fourth_trade_locked and stability_lock_active and not fourth_trade_allowed and not reentry_detected

    if safety_failed:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not reports_ready:
        status = "WARN"
        decision = REPORTS_MISSING_DECISION
    elif not state_locked:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env["operator_env_absent"]:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    engine_artifact_snapshot = {
        "artifact_hook_version": PROMPT_ID,
        "read_only": True,
        "dashboard_mode": artifact["dashboard_mode"],
        "lifecycle_state": artifact["lifecycle_state"],
        "telegram_message_key": artifact["telegram_message_key"],
        "telegram_lifecycle_message_key": artifact["telegram_lifecycle_message_key"],
        "telegram_message_text": artifact["telegram_message_text"],
        "visual_sl_tp_progress_bar": artifact["visual_sl_tp_progress_bar"],
        "visual_sl_tp_progress_pct": artifact["visual_sl_tp_progress_pct"],
        "progress_state": artifact["progress_state"],
        "aggregate_realized_pnl": artifact["aggregate_realized_pnl"],
        "balance_after": artifact["balance_after"],
        "total_realized_r_from_final_audits": artifact["total_realized_r_from_final_audits"],
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "flat_state_confirmed": snapshot["flat_state_confirmed"],
        "pending_orders_after": snapshot["pending_orders_after"],
    }

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "ENGINE_READ_ONLY_ARTIFACT_HOOK",
            "DASHBOARD_LIFECYCLE_ARTIFACT_READY" if reports_ready else "DASHBOARD_LIFECYCLE_ARTIFACT_PENDING",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
        ] + (["FLAT_LOCKED_ENGINE_VISIBLE"] if status == "PASS" else []),
        "blockers": blockers,
        "integration_preflight_ready": integration_ready,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "engine_artifact_hook_ready": status == "PASS",
        "paper_engine_hook_read_only": True,
        "paper_engine_artifact_hook_active": status == "PASS",
        "engine_artifact_snapshot": engine_artifact_snapshot,
        "dashboard_mode": artifact["dashboard_mode"],
        "lifecycle_state": artifact["lifecycle_state"],
        "telegram_message_key": artifact["telegram_message_key"],
        "telegram_lifecycle_message_key": artifact["telegram_lifecycle_message_key"],
        "telegram_payload_ready": artifact["telegram_payload_ready"],
        "telegram_update_ready": artifact["telegram_update_ready"],
        "visual_sl_tp_progress_bar_ready": artifact["visual_sl_tp_progress_bar_ready"],
        "visual_sl_tp_progress_bar": artifact["visual_sl_tp_progress_bar"],
        "visual_sl_tp_progress_pct": artifact["visual_sl_tp_progress_pct"],
        "progress_state": artifact["progress_state"],
        "submit_execution_events_total": artifact["submit_execution_events_total"],
        "close_execution_events_total": artifact["close_execution_events_total"],
        "aggregate_realized_pnl": artifact["aggregate_realized_pnl"],
        "balance_after": artifact["balance_after"],
        "total_realized_r_from_final_audits": artifact["total_realized_r_from_final_audits"],
        **snapshot,
        **env,
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_trade_allowed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "engine_mutation_allowed": False,
        "engine_runtime_hook_enabled": False,
        "runner_consolidation_allowed": False,
        "orders_submitted_by_engine_artifact_hook": 0,
        "positions_opened_by_engine_artifact_hook": 0,
        "positions_closed_by_engine_artifact_hook": 0,
        "paper_state_modified_by_engine_artifact_hook": False,
        "paper_status_modified_by_engine_artifact_hook": False,
        "broker_submit_called_by_engine_artifact_hook": False,
        "broker_close_called_by_engine_artifact_hook": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "recommended_next_patch": "29.4.4t-2 — Paper runner footer/console visibility consolidation",
        "next_step": "surface_engine_artifact_snapshot_in_paper_runner_footer",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
        "telegram_message_text": artifact["telegram_message_text"],
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report


def write_lsr_v2_engine_read_only_artifact_hook_report(
    data_dir: str | Path = "data",
    settings: EngineReadOnlyArtifactHookSettings | None = None,
) -> dict[str, Any]:
    if settings is None:
        return build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data_dir)
    return build_lsr_v2_engine_read_only_artifact_hook_report_from_files(
        data_dir=settings.data_dir,
        report_name=settings.report_name,
        jsonl_name=settings.jsonl_name,
    )
