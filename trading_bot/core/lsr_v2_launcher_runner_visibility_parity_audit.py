"""Prompt 29.4.4t-5 — LSR-v2 launcher/runner visibility parity audit.

Audit-only parity check between the read-only launcher dashboard banner
introduced in t-4 and the runner footer visibility model introduced in t-2.
The module reads existing artifacts only and writes its own report/jsonl.  It
never mutates paper_state/paper_status, starts schedulers, sends Telegram
messages, calls brokers, submits orders, closes positions, or unlocks a fourth
trade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

try:  # package import
    from .paper_once_runner_footer import load_lsr_v2_engine_artifact_hook_footer_summary
except Exception:  # pragma: no cover - script-style fallback
    from paper_once_runner_footer import load_lsr_v2_engine_artifact_hook_footer_summary  # type: ignore

PROMPT_ID = "29.4.4t-5"
EVENT_TYPE = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT"
REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
JSONL_NAME = "lsr_v2_launcher_runner_visibility_parity_audit.jsonl"

LAUNCHER_BANNER_REPORT_NAME = "lsr_v2_launcher_read_only_dashboard_banner_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

LAUNCHER_BANNER_PASS_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_VISIBILITY_PARITY_REPORTS_NOT_READY"
PARITY_MISMATCH_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_MISMATCH"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_VISIBILITY_PARITY_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_VISIBILITY_PARITY_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_VISIBILITY_PARITY_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = ("ARM", "EXECUTE", "ENABLE", "CONFIRMATION", "MAX_POSITIONS")

_PARITY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("lifecycle_state", "lifecycle_state", "lifecycle_state"),
    ("telegram_dashboard_ready", "telegram_dashboard_ready", "telegram_dashboard_ready"),
    ("telegram_payload_ready", "telegram_payload_ready", "telegram_payload_ready"),
    ("telegram_update_ready", "telegram_update_ready", "telegram_update_ready"),
    ("telegram_send_allowed", "telegram_send_allowed", "telegram_send_allowed"),
    ("telegram_network_called", "telegram_network_called", "telegram_network_called"),
    ("visual_sl_tp_progress_bar_ready", "visual_sl_tp_progress_bar_ready", "visual_sl_tp_progress_bar_ready"),
    ("visual_sl_tp_progress_bar", "visual_sl_tp_progress_bar", "visual_sl_tp_progress_bar"),
    ("fourth_trade_locked", "fourth_trade_locked", "fourth_trade_locked"),
    ("stability_lock_active", "stability_lock_active", "stability_lock_active"),
    ("fourth_trade_allowed", "fourth_trade_allowed", "fourth_trade_allowed"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready"}:
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
    if isinstance(value, dict):
        for key, row in value.items():
            if isinstance(row, dict):
                out = dict(row)
                out.setdefault(id_field, str(key))
                rows.append(out)
    elif isinstance(value, list):
        for idx, row in enumerate(value):
            if isinstance(row, dict):
                out = dict(row)
                out.setdefault(id_field, str(idx))
                rows.append(out)
    return rows


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")) for k in ("source", "strategy", "archetype", "tag", "order_source", "position_source", "metadata"))
    return "lsr_v2" in text.lower() or "LIQUIDITY_SWEEP_REVERSAL_V2" in text


def _is_open_position(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or "").strip().upper()
    if status in {"OPEN", "ACTIVE"}:
        return True
    if status in {"CLOSED", "FLAT", "CANCELLED", "CANCELED"}:
        return False
    return _safe_bool(row.get("open"), False) or _safe_bool(row.get("is_open"), False)


def _is_pending_order(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or "").strip().upper()
    if status in {"PENDING", "OPEN", "NEW", "PARTIALLY_FILLED"}:
        return True
    return False


def _operator_env_controls() -> dict[str, Any]:
    active: dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith(LSR_V2_OPERATOR_ENV_PREFIX):
            continue
        if not any(marker in key for marker in _OPERATOR_ENV_MARKERS):
            continue
        if str(value).strip() in {"", "0", "false", "False", "no", "NO", "off", "OFF"}:
            continue
        active[key] = str(value)
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


def _pass_report(report: Mapping[str, Any], decision: str) -> bool:
    return report.get("status") == "PASS" and report.get("decision") == decision


@dataclass(frozen=True)
class LauncherRunnerVisibilityParitySettings:
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


def _normalized_parity_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        lowered = text.lower()
        if lowered in {"true", "false", "yes", "no", "on", "off", "1", "0"}:
            return _safe_bool(text)
        return text
    return value


def _build_parity_matrix(launcher: Mapping[str, Any], runner_footer: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    matrix: dict[str, Any] = {}
    mismatches: list[str] = []
    for public_name, launcher_key, runner_key in _PARITY_FIELDS:
        left = _normalized_parity_value(launcher.get(launcher_key))
        right = _normalized_parity_value(runner_footer.get(runner_key))
        match = left == right
        matrix[public_name] = {
            "launcher": left,
            "runner_footer": right,
            "match": match,
        }
        if not match:
            mismatches.append(public_name)
    return matrix, mismatches


def build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(
    *,
    data_dir: str | Path = "data",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = LauncherRunnerVisibilityParitySettings(data_dir=str(data_dir), report_name=report_name, jsonl_name=jsonl_name)
    data = Path(data_dir)

    launcher = _read_json(data / LAUNCHER_BANNER_REPORT_NAME)
    engine_hook = _read_json(data / ENGINE_HOOK_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    runner_footer = load_lsr_v2_engine_artifact_hook_footer_summary(data)
    env = _operator_env_controls()
    state = _state_status_snapshot(paper_state, paper_status)

    launcher_ready = _pass_report(launcher, LAUNCHER_BANNER_PASS_DECISION)
    engine_hook_ready = _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
    lifecycle_ready = _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
    dashboard_ready = _pass_report(dashboard, DASHBOARD_PASS_DECISION)
    postmortem_ready = _pass_report(postmortem, POSTMORTEM_PASS_DECISION)

    parity_matrix, mismatches = _build_parity_matrix(launcher, runner_footer)
    parity_ok = not mismatches

    lifecycle_state = str(launcher.get("lifecycle_state") or runner_footer.get("lifecycle_state") or "")
    fourth_locked = _safe_bool(launcher.get("fourth_trade_locked"), _safe_bool(runner_footer.get("fourth_trade_locked"), False))
    stability_lock_active = _safe_bool(launcher.get("stability_lock_active"), _safe_bool(runner_footer.get("stability_lock_active"), False))
    fourth_allowed = _safe_bool(launcher.get("fourth_trade_allowed"), _safe_bool(runner_footer.get("fourth_trade_allowed"), True))
    reentry_detected = _safe_bool(launcher.get("fourth_submit_or_reentry_detected"), _safe_bool(runner_footer.get("fourth_submit_or_reentry_detected"), False))

    live_enabled = _safe_bool(launcher.get("live_enabled"), _safe_bool(runner_footer.get("live_enabled"), _safe_bool(paper_status.get("live_enabled"), False)))
    testnet_enabled = _safe_bool(launcher.get("testnet_enabled"), _safe_bool(runner_footer.get("testnet_enabled"), _safe_bool(paper_status.get("testnet_enabled"), False)))
    exchange_broker_enabled = _safe_bool(launcher.get("exchange_broker_enabled"), _safe_bool(runner_footer.get("exchange_broker_enabled"), _safe_bool(paper_status.get("exchange_broker_enabled"), False)))
    operational_unlock_allowed = _safe_bool(launcher.get("operational_unlock_allowed"), _safe_bool(runner_footer.get("operational_unlock_allowed"), False))
    promotion_ready = _safe_bool(launcher.get("promotion_ready"), _safe_bool(runner_footer.get("promotion_ready"), False))

    reports_ready = launcher_ready and engine_hook_ready and lifecycle_ready and dashboard_ready and postmortem_ready
    state_locked = (
        state["flat_state_confirmed"]
        and state["pending_orders_clear"]
        and state["paper_state_status_consistency"]
        and lifecycle_state == "FLAT_LOCKED"
        and fourth_locked
        and stability_lock_active
        and not fourth_allowed
        and not reentry_detected
    )
    safety_failed = live_enabled or testnet_enabled or exchange_broker_enabled or operational_unlock_allowed or promotion_ready

    blockers: list[str] = []
    if not launcher_ready:
        blockers.append("launcher_banner_not_ready")
    if not engine_hook_ready:
        blockers.append("engine_artifact_hook_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if mismatches:
        blockers.append("launcher_runner_visibility_mismatch")
        blockers.extend([f"mismatch:{name}" for name in mismatches])
    if not state["flat_state_confirmed"]:
        blockers.append("paper_state_or_status_not_flat")
    if not state["pending_orders_clear"]:
        blockers.append("pending_orders_not_clear")
    if not state["paper_state_status_consistency"]:
        blockers.append("paper_state_status_inconsistent")
    if lifecycle_state != "FLAT_LOCKED" or not fourth_locked or not stability_lock_active or fourth_allowed:
        blockers.append("flat_lock_not_enforced")
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

    if safety_failed:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not reports_ready:
        status = "WARN"
        decision = REPORTS_NOT_READY_DECISION
    elif not parity_ok:
        status = "WARN"
        decision = PARITY_MISMATCH_DECISION
    elif not state_locked:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env["operator_env_absent"]:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
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
            "LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT",
            "READ_ONLY",
            "NO_LAUNCHER_MUTATION",
            "NO_RUNNER_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["VISIBILITY_PARITY_READY"] if status == "PASS" else []),
        "blockers": blockers,
        "visibility_parity_audit_ready": status == "PASS",
        "launcher_runner_visibility_parity_ok": parity_ok and reports_ready and state_locked and env["operator_env_absent"] and not safety_failed,
        "visibility_mismatch_detected": bool(mismatches),
        "visibility_mismatch_fields": mismatches,
        "visibility_parity_matrix": parity_matrix,
        "launcher_banner_ready": launcher_ready,
        "runner_footer_ready": engine_hook_ready,
        "engine_hook_ready": engine_hook_ready,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": str(launcher.get("dashboard_mode") or engine_hook.get("dashboard_mode") or dashboard.get("dashboard_mode") or ""),
        "telegram_payload_ready": _safe_bool(launcher.get("telegram_payload_ready"), False),
        "telegram_update_ready": _safe_bool(launcher.get("telegram_update_ready"), False),
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "visual_sl_tp_progress_bar_ready": _safe_bool(launcher.get("visual_sl_tp_progress_bar_ready"), False),
        "visual_sl_tp_progress_bar": str(launcher.get("visual_sl_tp_progress_bar") or ""),
        **state,
        **env,
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(launcher.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(launcher.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(launcher.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": _safe_float(launcher.get("balance_after"), _safe_float(state.get("balance_after"), 0.0)),
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_allowed,
        "fourth_trade_locked": fourth_locked,
        "stability_lock_active": stability_lock_active,
        "launcher_banner_text_present": bool(str(launcher.get("launcher_banner_text") or "")),
        "runner_footer_model_source": ENGINE_HOOK_REPORT_NAME,
        "launcher_report_source": LAUNCHER_BANNER_REPORT_NAME,
        "orders_submitted_by_launcher_runner_parity_audit": 0,
        "positions_opened_by_launcher_runner_parity_audit": 0,
        "positions_closed_by_launcher_runner_parity_audit": 0,
        "paper_state_modified_by_launcher_runner_parity_audit": False,
        "paper_status_modified_by_launcher_runner_parity_audit": False,
        "broker_submit_called_by_launcher_runner_parity_audit": False,
        "broker_close_called_by_launcher_runner_parity_audit": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "recommended_next_patch": "29.4.4t-6 — Launcher/runner read-only handoff consolidation preflight",
        "next_step": "validate_visibility_parity_then_prepare_read_only_handoff_preflight",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report


def run_lsr_v2_launcher_runner_visibility_parity_audit(*, data_dir: str | Path = "data") -> dict[str, Any]:
    return build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data_dir)
