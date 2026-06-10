from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from trading_bot.strategy_runtime.selected_strategy_shadow_outcome_tracker import build_outcome_tracking_stub
from trading_bot.strategy_runtime.strategy_config_store import utc_now


def journal_path(data_dir: Path) -> Path:
    return data_dir / "selected_strategy_shadow_signal_journal.jsonl"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return out if out == out else None
    except Exception:
        return None


def build_shadow_journal_event(
    *,
    execution_report: dict[str, Any],
    asset: str,
    timeframe: str,
    mode: str = "paper",
) -> dict[str, Any]:
    signal = dict(execution_report.get("signal") or {})
    active = str(execution_report.get("active_strategy") or signal.get("strategy") or "invalid")
    event = {
        "event_id": f"shadow_{uuid4().hex}",
        "created_at": utc_now(),
        "active_strategy": active,
        "active_strategy_label": execution_report.get("active_strategy_label") or signal.get("strategy_label") or active,
        "mode": mode,
        "asset": asset,
        "timeframe": timeframe,
        "signal": signal.get("signal", "WAIT"),
        "score": _safe_float(signal.get("score")) or 0.0,
        "shadow_only": True,
        "would_trade": False,
        "can_trade": False,
        "entry_price": signal.get("entry_price"),
        "sl": signal.get("sl"),
        "tp": signal.get("tp"),
        "risk_pct": signal.get("risk_pct"),
        "conditions": list(signal.get("conditions") or []),
        "block_reasons": list(signal.get("block_reasons") or ["shadow_signal_execution_only"]),
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "paper_trading_activation_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
        "would_submit": False,
        "would_close": False,
    }
    if "shadow_signal_execution_only" not in event["block_reasons"]:
        event["block_reasons"].append("shadow_signal_execution_only")
    event["outcome_tracking"] = build_outcome_tracking_stub(event)
    return event


def append_shadow_event(data_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    path = journal_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": "shadow_journal_not_writable",
            "error": str(exc),
            "path": str(path),
            "event": event,
        }
    return {
        "status": "OK",
        "reason": "shadow_event_recorded",
        "path": str(path),
        "event": event,
    }


def read_shadow_events(data_dir: Path, *, tail: int = 5000) -> list[dict[str, Any]]:
    path = journal_path(data_dir)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if tail > 0:
        lines = lines[-tail:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                events.append(payload)
        except Exception:
            continue
    return events


def latest_shadow_event(data_dir: Path) -> dict[str, Any]:
    events = read_shadow_events(data_dir, tail=1)
    return events[-1] if events else {}
