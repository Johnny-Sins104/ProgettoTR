"""Prompt 29.4.4t — LSR-v2 Paper Engine integration planning preflight.

Audit-only planning layer for consolidating the isolated LSR-v2 supervised paper
runners into the main paper engine architecture. This module deliberately does
not integrate runtime hooks yet: it inspects the current project state, verifies
that the three-trade LSR-v2 cycle is closed/locked, maps the required engine
hooks, and writes a preflight report for the next consolidation patch.

Safety contract: no order submission, no position opening/closing, no broker
calls, no Telegram network sends, no scheduler start, no paper_state/paper_status
mutation, no live/testnet/exchange broker enablement.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t"
EVENT_TYPE = "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT"
REPORT_NAME = "lsr_v2_paper_engine_integration_preflight_report.json"
JSONL_NAME = "lsr_v2_paper_engine_integration_preflight.jsonl"

LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"
PASS_DECISION = "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY"
REPORTS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_PREFLIGHT_REPORTS_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_PREFLIGHT_STATE_NOT_LOCKED"
SOURCE_HOOKS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_PREFLIGHT_SOURCE_HOOKS_MISSING"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_PREFLIGHT_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_ENGINE_PREFLIGHT_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM",
    "EXECUTE",
    "ENABLE",
    "CONFIRMATION",
    "MAX_POSITIONS",
)

SOURCE_TARGETS = {
    "paper_engine": "trading_bot/core/paper_engine.py",
    "run_paper_trading": "trading_bot/run_paper_trading.py",
    "avvia_bot_live": "trading_bot/avvia_bot_live.py",
}

REQUIRED_SOURCE_MARKERS = {
    "paper_engine": (
        "PaperTradingEngine",
        "lsr_v2",
        "write_lsr_v2_runtime_bridge_report",
    ),
    "run_paper_trading": (
        "PaperTradingEngine",
        "--once",
        "lsr-v2",
    ),
    "avvia_bot_live": (
        "paper_main",
        "--live",
        "--mode=live",
    ),
}

INTEGRATION_PLAN = [
    {
        "phase": "29.4.4t-1",
        "name": "engine-safe read-only lifecycle artifact hook",
        "target": "core/paper_engine.py",
        "action": "write/read LSR-v2 dashboard/lifecycle artifacts from engine finalization without changing order routing",
        "safety": "no submit, no close, no scheduler, no Telegram send",
    },
    {
        "phase": "29.4.4t-2",
        "name": "paper runner visibility consolidation",
        "target": "run_paper_trading.py",
        "action": "surface dashboard/lifecycle status in --once footer and operator console",
        "safety": "read-only console/report output",
    },
    {
        "phase": "29.4.4t-3",
        "name": "launcher dashboard preflight wiring",
        "target": "avvia_bot_live.py / launcher batch",
        "action": "make paper launcher aware of dashboard/lifecycle monitor readiness while live remains refused",
        "safety": "paper-only, no live/testnet/exchange broker",
    },
    {
        "phase": "29.4.4t-4",
        "name": "temporary runner deprecation map",
        "target": "isolated LSR-v2 runners",
        "action": "map which isolated preflight/monitor runners become engine stages and which stay diagnostic tools",
        "safety": "no removal until parity reports pass",
    },
]

RUNNER_CONSOLIDATION_MAP = [
    {
        "runner": "run_lsr_v2_three_trade_postmortem_stability_lock.py",
        "future_engine_stage": "post-cycle stability lock report",
        "mode": "read-only artifact",
    },
    {
        "runner": "run_lsr_v2_telegram_trade_dashboard.py",
        "future_engine_stage": "dashboard payload builder",
        "mode": "read-only artifact / Telegram send remains gated",
    },
    {
        "runner": "run_lsr_v2_trade_lifecycle_auto_monitor.py",
        "future_engine_stage": "lifecycle classifier",
        "mode": "monitoring-only until scheduler/send patch",
    },
    {
        "runner": "run_lsr_v2_third_trade_close_execution.py",
        "future_engine_stage": "historical supervised close boundary",
        "mode": "closed cycle artifact; no re-entry",
    },
]


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


def _row_source(row: Mapping[str, Any]) -> str:
    meta = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
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
    text = " ".join(
        [
            _row_source(row),
            str(row.get("profile_name") or ""),
            str(row.get("selected_overlay_id") or ""),
            str(row.get("trade_sequence") or ""),
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


def _inspect_source_hooks(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    targets: dict[str, Any] = {}
    missing_files: list[str] = []
    missing_markers: dict[str, list[str]] = {}
    for name, rel in SOURCE_TARGETS.items():
        path = root / rel
        exists = path.exists()
        text = ""
        if exists:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
        else:
            missing_files.append(rel)
        markers = list(REQUIRED_SOURCE_MARKERS.get(name, ()))
        absent = [marker for marker in markers if marker.lower() not in text.lower()]
        if absent:
            missing_markers[name] = absent
        targets[name] = {
            "path": rel,
            "exists": exists,
            "required_markers": markers,
            "missing_markers": absent,
            "lsr_v2_mentions": text.lower().count("lsr_v2"),
            "paper_only_guard_present": ("--live" in text and "disabled" in text.lower()) or "paper-only" in text.lower(),
        }
    return {
        "source_targets": targets,
        "source_files_present": len(missing_files) == 0,
        "missing_source_files": missing_files,
        "required_source_markers_present": len(missing_markers) == 0,
        "missing_source_markers": missing_markers,
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


@dataclass(frozen=True)
class IntegrationPreflightSettings:
    data_dir: str = "data"
    project_root: str = "."
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    fail_closed: bool = True

    @property
    def report_path(self) -> Path:
        return Path(self.data_dir) / self.report_name

    @property
    def jsonl_path(self) -> Path:
        return Path(self.data_dir) / self.jsonl_name


def build_lsr_v2_paper_engine_integration_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = IntegrationPreflightSettings(
        data_dir=str(data_dir),
        project_root=str(project_root),
        report_name=report_name,
        jsonl_name=jsonl_name,
    )
    data = Path(data_dir)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    hooks = _inspect_source_hooks(project_root)
    snapshot = _state_status_snapshot(paper_state, paper_status)

    lifecycle_ready = lifecycle.get("status") == "PASS" and lifecycle.get("decision") == LIFECYCLE_PASS_DECISION
    dashboard_ready = dashboard.get("status") == "PASS" and dashboard.get("decision") == DASHBOARD_PASS_DECISION
    postmortem_ready = postmortem.get("status") == "PASS" and postmortem.get("decision") == POSTMORTEM_PASS_DECISION

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
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
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
    if not hooks["source_files_present"]:
        blockers.append("source_files_missing")
    if not hooks["required_source_markers_present"]:
        blockers.append("source_markers_missing")
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
    reports_ready = lifecycle_ready and dashboard_ready and postmortem_ready
    state_locked = snapshot["flat_state_confirmed"] and snapshot["pending_orders_clear"] and snapshot["paper_state_status_consistency"] and fourth_trade_locked and stability_lock_active and not fourth_trade_allowed and not reentry_detected
    sources_ready = hooks["source_files_present"] and hooks["required_source_markers_present"]

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
    elif not sources_ready:
        status = "WARN"
        decision = SOURCE_HOOKS_MISSING_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "INTEGRATION_PLANNING_ONLY",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "PAPER_ENGINE_PREFLIGHT",
        ] + (["READY_FOR_ENGINE_CONSOLIDATION_PLANNING"] if status == "PASS" else []),
        "blockers": blockers,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "lifecycle_state": lifecycle.get("lifecycle_state", ""),
        "dashboard_mode": dashboard.get("dashboard_mode", ""),
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(lifecycle.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(lifecycle.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(lifecycle.get("aggregate_realized_pnl"), 0.0)),
        "pnl_reconciliation_ok": _safe_bool(postmortem.get("pnl_reconciliation_ok"), _safe_bool(lifecycle.get("pnl_reconciliation_ok"), False)),
        **snapshot,
        **env,
        **hooks,
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_trade_allowed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "integration_preflight_ready": status == "PASS",
        "engine_integration_allowed": False,
        "engine_mutation_allowed": False,
        "runner_consolidation_allowed": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "orders_submitted_by_integration_preflight": 0,
        "positions_opened_by_integration_preflight": 0,
        "positions_closed_by_integration_preflight": 0,
        "paper_state_modified_by_integration_preflight": False,
        "paper_status_modified_by_integration_preflight": False,
        "broker_submit_called_by_integration_preflight": False,
        "broker_close_called_by_integration_preflight": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "integration_plan": INTEGRATION_PLAN,
        "runner_consolidation_map": RUNNER_CONSOLIDATION_MAP,
        "recommended_next_patch": "29.4.4t-1 — Engine read-only dashboard/lifecycle artifact hook",
        "next_step": "prepare_read_only_engine_hook_after_preflight_pass",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report
