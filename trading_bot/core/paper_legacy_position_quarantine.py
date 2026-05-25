"""Prompt 29.4.4r-2 legacy paper position quarantine / clean-state preflight.

This module sanitizes paper-only state after the 29.4.4r-OBS finding that
legacy ``ScoreOnly+Meta_OK`` paper execution created orders/positions outside
of the guarded routing/candidate/handoff path.

The module is intentionally state-management only.  It does not submit orders,
does not open positions, does not contact any broker, and does not enable
live/testnet/exchange execution.  Reset actions require an explicit CLI flag and
create backups before changing active files.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import shutil

try:
    from config import Config
except Exception:  # pragma: no cover - tests can pass a settings object directly
    Config = object()  # type: ignore[assignment]

PROMPT_ID = "29.4.4r-2"
REPORT_NAME = "paper_legacy_position_quarantine_report.json"
BACKUP_DIR_NAME = "paper_legacy_quarantine_backups"
EVENT_QUARANTINED = "PAPER_LEGACY_POSITION_QUARANTINED"
EVENT_ORDER_QUARANTINED = "PAPER_LEGACY_ORDER_QUARANTINED"
EVENT_STATE_RESET = "PAPER_LEGACY_STATE_RESET"
REPORT_READY_DECISION = "LEGACY_PAPER_POSITION_QUARANTINE_READY_DIAGNOSTIC"
CLEAN_READY_DECISION = "PAPER_CLEAN_STATE_PREFLIGHT_READY"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
STATE_FILES = (
    "paper_state.json",
    "paper_status.json",
    "paper_position_monitor.json",
    "paper_order_leakage_guard_report.json",
    "paper_unlock_8h_dry_run_observation_report.json",
    "paper_unlock_4h_observation_report.json",
)
LOG_FILES = ("paper_events.jsonl", "telegram_audit.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_event(path: Path, event_type: str, **payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": utc_now_iso(), "event_type": event_type, **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    return _as_mapping(item.get("metadata"))


def _is_legacy_score_meta_metadata(metadata: Mapping[str, Any]) -> bool:
    combination = str(metadata.get("combination") or metadata.get("archetype") or metadata.get("setup_archetype") or "")
    paper_unlock = _safe_bool(metadata.get("paper_unlock"))
    unlock_profile = str(metadata.get("unlock_profile") or metadata.get("unlock_tag") or "")
    guarded = _safe_bool(metadata.get("guarded_supervised_execution")) or _safe_bool(metadata.get("candidate_ready"))
    score_meta = "ScoreOnly" in combination or "Meta_OK" in combination
    return bool(score_meta and not paper_unlock and not unlock_profile and not guarded)


def _is_legacy_order(order: Mapping[str, Any]) -> bool:
    return _is_legacy_score_meta_metadata(_metadata(order))


def _is_legacy_position(position: Mapping[str, Any]) -> bool:
    return _is_legacy_score_meta_metadata(_metadata(position))


def _position_unrealized_from_status(status_data: Mapping[str, Any], position: Mapping[str, Any]) -> float:
    symbol = str(position.get("symbol") or "")
    entry = _safe_float(position.get("entry_price"))
    qty = _safe_float(position.get("qty"))
    side = str(position.get("side") or "")
    monitor = _as_mapping(status_data.get("position_monitor"))
    raw_account = _as_mapping(_as_mapping(monitor.get("account")).get("raw"))
    for item in raw_account.get("positions", []) if isinstance(raw_account.get("positions"), list) else []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("symbol") or "") == symbol:
            return _safe_float(item.get("unrealized_pnl"))
    for item in status_data.get("positions", []) if isinstance(status_data.get("positions"), list) else []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("symbol") or "") == symbol:
            return _safe_float(item.get("unrealized_pnl"))
    # If no mark is available, avoid inventing PnL.
    if not symbol or entry <= 0 or qty <= 0 or side not in {"BUY", "SELL"}:
        return 0.0
    return 0.0


@dataclass(frozen=True)
class LegacyPositionQuarantineSettings:
    report_name: str = REPORT_NAME
    backup_dir_name: str = BACKUP_DIR_NAME
    events_name: str = "paper_events.jsonl"
    state_name: str = "paper_state.json"
    status_name: str = "paper_status.json"
    monitor_name: str = "paper_position_monitor.json"
    prompt: str = PROMPT_ID

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "LegacyPositionQuarantineSettings":
        return cls(
            report_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            backup_dir_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_BACKUP_DIR", BACKUP_DIR_NAME) or BACKUP_DIR_NAME),
            events_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            state_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_STATE_NAME", "paper_state.json") or "paper_state.json"),
            status_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            monitor_name=str(getattr(cfg, "PAPER_LEGACY_QUARANTINE_MONITOR_NAME", "paper_position_monitor.json") or "paper_position_monitor.json"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_name": self.report_name,
            "backup_dir_name": self.backup_dir_name,
            "events_name": self.events_name,
            "state_name": self.state_name,
            "status_name": self.status_name,
            "monitor_name": self.monitor_name,
            "prompt": self.prompt,
        }


def _collect_legacy_state(base: Path, settings: LegacyPositionQuarantineSettings) -> dict[str, Any]:
    state = _read_json(base / settings.state_name, {})
    status = _read_json(base / settings.status_name, {})
    orders = _as_mapping(state.get("orders"))
    positions = _as_mapping(state.get("positions"))

    legacy_orders: list[dict[str, Any]] = []
    legacy_positions: list[dict[str, Any]] = []
    legacy_open_positions: list[dict[str, Any]] = []
    legacy_closed_positions: list[dict[str, Any]] = []
    legacy_realized_pnl = 0.0
    legacy_unrealized_pnl = 0.0
    affected_symbols: set[str] = set()
    affected_cycles: set[str] = set()

    for order_id, order_value in orders.items():
        if not isinstance(order_value, Mapping) or not _is_legacy_order(order_value):
            continue
        md = _metadata(order_value)
        symbol = str(order_value.get("symbol") or "")
        cycle_id = str(md.get("cycle_id") or "")
        if symbol:
            affected_symbols.add(symbol)
        if cycle_id:
            affected_cycles.add(cycle_id)
        legacy_orders.append(
            {
                "order_id": str(order_id),
                "symbol": symbol,
                "side": str(order_value.get("side") or ""),
                "status": str(order_value.get("status") or ""),
                "cycle_id": cycle_id,
                "combination": str(md.get("combination") or ""),
                "paper_unlock": _safe_bool(md.get("paper_unlock")),
                "unlock_profile": md.get("unlock_profile"),
                "filled_price": order_value.get("filled_price"),
                "qty": order_value.get("qty"),
                "created_at": order_value.get("created_at"),
            }
        )

    for position_id, position_value in positions.items():
        if not isinstance(position_value, Mapping) or not _is_legacy_position(position_value):
            continue
        md = _metadata(position_value)
        status_value = str(position_value.get("status") or "")
        symbol = str(position_value.get("symbol") or "")
        cycle_id = str(md.get("cycle_id") or "")
        realized = _safe_float(position_value.get("realized_pnl"))
        unrealized = 0.0 if status_value != "OPEN" else _position_unrealized_from_status(status, position_value)
        legacy_realized_pnl += realized
        legacy_unrealized_pnl += unrealized
        if symbol:
            affected_symbols.add(symbol)
        if cycle_id:
            affected_cycles.add(cycle_id)
        sample = {
            "position_id": str(position_id),
            "symbol": symbol,
            "side": str(position_value.get("side") or ""),
            "status": status_value,
            "cycle_id": cycle_id,
            "combination": str(md.get("combination") or ""),
            "source_order_id": str(md.get("source_order_id") or ""),
            "entry_price": position_value.get("entry_price"),
            "qty": position_value.get("qty"),
            "stop_loss": position_value.get("stop_loss"),
            "take_profit": position_value.get("take_profit"),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "opened_at": position_value.get("opened_at"),
            "closed_at": position_value.get("closed_at"),
            "close_reason": position_value.get("close_reason"),
        }
        legacy_positions.append(sample)
        if status_value == "OPEN":
            legacy_open_positions.append(sample)
        elif status_value == "CLOSED":
            legacy_closed_positions.append(sample)

    return {
        "state": state,
        "status": status,
        "legacy_orders": legacy_orders,
        "legacy_positions": legacy_positions,
        "legacy_open_positions": legacy_open_positions,
        "legacy_closed_positions": legacy_closed_positions,
        "legacy_orders_count": len(legacy_orders),
        "legacy_positions_count": len(legacy_positions),
        "legacy_open_positions_count": len(legacy_open_positions),
        "legacy_closed_positions_count": len(legacy_closed_positions),
        "legacy_realized_pnl": round(legacy_realized_pnl, 10),
        "legacy_unrealized_pnl": round(legacy_unrealized_pnl, 10),
        "affected_symbols": sorted(affected_symbols),
        "affected_cycles": sorted(affected_cycles),
        "current_open_positions": _safe_int(state.get("positions_opened") or status.get("open_positions"), len([p for p in positions.values() if isinstance(p, Mapping) and p.get("status") == "OPEN"])),
        "balance": _safe_float(state.get("balance"), _safe_float(status.get("balance"), 1000.0)),
        "paper_account_realized_pnl": _safe_float(state.get("realized_pnl"), _safe_float(status.get("realized_pnl"), 0.0)),
        "paper_account_unrealized_pnl": _safe_float(status.get("unrealized_pnl"), 0.0),
        "initial_balance": _safe_float(state.get("initial_balance"), 1000.0),
        "paper_state_exists": (base / settings.state_name).exists(),
        "paper_status_exists": (base / settings.status_name).exists(),
    }


def create_quarantine_backup(base: str | Path = "data", settings: LegacyPositionQuarantineSettings | None = None) -> Path:
    settings = settings or LegacyPositionQuarantineSettings.from_config()
    base_path = Path(base)
    backup_root = base_path / settings.backup_dir_name
    backup_dir = backup_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in (*STATE_FILES, *LOG_FILES):
        src = base_path / name
        if src.exists():
            shutil.copy2(src, backup_dir / name)
    manifest = {
        "prompt": PROMPT_ID,
        "created_at": utc_now_iso(),
        "backup_dir": str(backup_dir),
        "files": sorted(p.name for p in backup_dir.iterdir() if p.is_file()),
    }
    _write_json(backup_dir / "BACKUP_MANIFEST_29_4_4R2.json", manifest)
    return backup_dir


def build_legacy_position_quarantine_report(
    base: str | Path = "data",
    settings: LegacyPositionQuarantineSettings | None = None,
    *,
    mode: str = "report_only",
    backup_dir: str | None = None,
    reset_applied: bool = False,
    quarantine_applied: bool = False,
) -> dict[str, Any]:
    settings = settings or LegacyPositionQuarantineSettings.from_config()
    base_path = Path(base)
    collected = _collect_legacy_state(base_path, settings)
    clean_state_ready = bool(
        collected["legacy_open_positions_count"] == 0
        and collected["current_open_positions"] == 0
    )
    status = "PASS" if clean_state_ready else "WARN"
    decision_status = CLEAN_READY_DECISION if clean_state_ready else KEEP_DECISION
    return {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": {
            "status": decision_status,
            "mode": mode,
            "legacy_contamination_detected": bool(collected["legacy_orders_count"] or collected["legacy_positions_count"]),
            "legacy_orders_count": collected["legacy_orders_count"],
            "legacy_positions_count": collected["legacy_positions_count"],
            "legacy_open_positions_count": collected["legacy_open_positions_count"],
            "legacy_closed_positions_count": collected["legacy_closed_positions_count"],
            "current_open_positions": collected["current_open_positions"],
            "safe_cleanup_available": bool(collected["legacy_orders_count"] or collected["legacy_positions_count"]),
            "clean_state_ready": clean_state_ready,
            "quarantine_applied": quarantine_applied,
            "reset_applied": reset_applied,
            "backup_dir": backup_dir or "",
            "operational_unlock_allowed": False,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
        },
        "legacy_summary": {
            "legacy_orders_count": collected["legacy_orders_count"],
            "legacy_positions_count": collected["legacy_positions_count"],
            "legacy_open_positions_count": collected["legacy_open_positions_count"],
            "legacy_closed_positions_count": collected["legacy_closed_positions_count"],
            "legacy_realized_pnl": collected["legacy_realized_pnl"],
            "legacy_unrealized_pnl": collected["legacy_unrealized_pnl"],
            "paper_account_realized_pnl": collected["paper_account_realized_pnl"],
            "paper_account_unrealized_pnl": collected["paper_account_unrealized_pnl"],
            "affected_symbols": collected["affected_symbols"],
            "affected_cycles": collected["affected_cycles"],
            "open_positions": collected["legacy_open_positions"],
            "closed_positions": collected["legacy_closed_positions"],
            "orders": collected["legacy_orders"],
        },
        "safety_checks": {
            "live_blocked": True,
            "testnet_blocked": True,
            "exchange_broker_blocked": True,
            "operational_unlock_blocked": True,
            "no_active_legacy_open_positions": collected["legacy_open_positions_count"] == 0,
            "paper_state_open_positions_zero": collected["current_open_positions"] == 0,
            "reset_requires_confirm_reset": True,
            "state_backup_created_before_mutation": bool(backup_dir) if (reset_applied or quarantine_applied) else True,
        },
        "settings": settings.to_dict(),
        "generated_at": utc_now_iso(),
    }


def write_legacy_position_quarantine_report(
    base: str | Path = "data",
    settings: LegacyPositionQuarantineSettings | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    settings = settings or LegacyPositionQuarantineSettings.from_config()
    report = build_legacy_position_quarantine_report(base, settings, **kwargs)
    _write_json(Path(base) / settings.report_name, report)
    return report


def quarantine_legacy_positions(
    base: str | Path = "data",
    settings: LegacyPositionQuarantineSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LegacyPositionQuarantineSettings.from_config()
    base_path = Path(base)
    backup_dir = create_quarantine_backup(base_path, settings)
    state = _read_json(base_path / settings.state_name, {})
    orders = _as_mapping(state.get("orders"))
    positions = _as_mapping(state.get("positions"))
    now = utc_now_iso()
    quarantined_orders = 0
    quarantined_positions = 0
    for order_id, order in orders.items():
        if not isinstance(order, dict) or not _is_legacy_order(order):
            continue
        md = _metadata(order)
        md.update(
            {
                "legacy_contaminated": True,
                "legacy_quarantined": True,
                "legacy_quarantine_prompt": PROMPT_ID,
                "legacy_quarantined_at": now,
                "excluded_from_guarded_diagnostics": True,
                "order_execution_allowed": False,
            }
        )
        order["metadata"] = md
        quarantined_orders += 1
        _append_event(base_path / settings.events_name, EVENT_ORDER_QUARANTINED, prompt=PROMPT_ID, order_id=str(order_id), symbol=order.get("symbol"), side=order.get("side"), source_path="legacy_score_meta")
    for position_id, position in positions.items():
        if not isinstance(position, dict) or not _is_legacy_position(position):
            continue
        md = _metadata(position)
        md.update(
            {
                "legacy_contaminated": True,
                "legacy_quarantined": True,
                "legacy_quarantine_prompt": PROMPT_ID,
                "legacy_quarantined_at": now,
                "excluded_from_guarded_diagnostics": True,
                "position_execution_allowed": False,
            }
        )
        position["metadata"] = md
        quarantined_positions += 1
        _append_event(base_path / settings.events_name, EVENT_QUARANTINED, prompt=PROMPT_ID, position_id=str(position_id), symbol=position.get("symbol"), side=position.get("side"), status=position.get("status"), source_path="legacy_score_meta")
    state["orders"] = orders
    state["positions"] = positions
    state["updated_at"] = now
    state["legacy_quarantine"] = {
        "prompt": PROMPT_ID,
        "quarantined_at": now,
        "quarantined_orders": quarantined_orders,
        "quarantined_positions": quarantined_positions,
        "backup_dir": str(backup_dir),
    }
    _write_json(base_path / settings.state_name, state)
    return write_legacy_position_quarantine_report(base_path, settings, mode="quarantine", backup_dir=str(backup_dir), quarantine_applied=True)


def _empty_monitor(initial_balance: float) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "mode": "paper",
        "status": "EMPTY",
        "open_position_count": 0,
        "positions": [],
        "account": {
            "mode": "paper",
            "balance": initial_balance,
            "equity": initial_balance,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "drawdown_pct": 0.0,
            "open_positions": 0,
            "pending_orders": 0,
            "is_paused": False,
            "kill_switch": False,
            "raw": {"positions": [], "balance": initial_balance, "equity": initial_balance, "realized_pnl": 0.0, "unrealized_pnl": 0.0, "open_positions": 0, "pending_orders": 0},
        },
    }


def reset_legacy_paper_state(
    base: str | Path = "data",
    settings: LegacyPositionQuarantineSettings | None = None,
    *,
    confirm_reset: bool = False,
) -> dict[str, Any]:
    if not confirm_reset:
        raise ValueError("reset_legacy_paper_state requires confirm_reset=True")
    settings = settings or LegacyPositionQuarantineSettings.from_config()
    base_path = Path(base)
    collected_before = _collect_legacy_state(base_path, settings)
    backup_dir = create_quarantine_backup(base_path, settings)
    initial_balance = _safe_float(collected_before.get("initial_balance"), 1000.0) or 1000.0
    now = utc_now_iso()
    clean_state = {
        "updated_at": now,
        "initial_balance": initial_balance,
        "balance": initial_balance,
        "realized_pnl": 0.0,
        "peak_balance": initial_balance,
        "drawdown_pct": 0.0,
        "is_paused": False,
        "kill_switch": False,
        "state_loaded": True,
        "restored_at": None,
        "orders": {},
        "positions": {},
        "legacy_reset": {
            "prompt": PROMPT_ID,
            "reset_at": now,
            "backup_dir": str(backup_dir),
            "legacy_orders_count_before_reset": collected_before["legacy_orders_count"],
            "legacy_open_positions_count_before_reset": collected_before["legacy_open_positions_count"],
            "legacy_realized_pnl_before_reset": collected_before["legacy_realized_pnl"],
            "legacy_unrealized_pnl_before_reset": collected_before["legacy_unrealized_pnl"],
            "paper_account_realized_pnl_before_reset": collected_before["paper_account_realized_pnl"],
            "paper_account_unrealized_pnl_before_reset": collected_before["paper_account_unrealized_pnl"],
        },
    }
    _write_json(base_path / settings.state_name, clean_state)

    status = _read_json(base_path / settings.status_name, {})
    if not isinstance(status, dict):
        status = {}
    status.update(
        {
            "updated_at": now,
            "balance": initial_balance,
            "equity": initial_balance,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "drawdown_pct": 0.0,
            "open_positions": 0,
            "pending_orders": 0,
            "positions": [],
            "is_paused": False,
            "kill_switch": False,
            "legacy_quarantine_clean_state": {
                "prompt": PROMPT_ID,
                "reset_at": now,
                "backup_dir": str(backup_dir),
                "status": "CLEAN_STATE_READY",
            },
        }
    )
    status["position_monitor"] = _empty_monitor(initial_balance)
    _write_json(base_path / settings.status_name, status)
    _write_json(base_path / settings.monitor_name, _empty_monitor(initial_balance))

    # Rotate active paper events after backing them up, so future guard/observation
    # reports no longer fail on historical contaminated events.
    events_path = base_path / settings.events_name
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text("", encoding="utf-8")
    _append_event(
        events_path,
        EVENT_STATE_RESET,
        prompt=PROMPT_ID,
        backup_dir=str(backup_dir),
        legacy_orders_count_before_reset=collected_before["legacy_orders_count"],
        legacy_open_positions_count_before_reset=collected_before["legacy_open_positions_count"],
        legacy_realized_pnl_before_reset=collected_before["legacy_realized_pnl"],
        legacy_unrealized_pnl_before_reset=collected_before["legacy_unrealized_pnl"],
        paper_account_realized_pnl_before_reset=collected_before["paper_account_realized_pnl"],
        paper_account_unrealized_pnl_before_reset=collected_before["paper_account_unrealized_pnl"],
        live_allowed=False,
        testnet_allowed=False,
        exchange_broker_allowed=False,
        operational_unlock_allowed=False,
    )
    return write_legacy_position_quarantine_report(base_path, settings, mode="reset_paper_state", backup_dir=str(backup_dir), reset_applied=True)
