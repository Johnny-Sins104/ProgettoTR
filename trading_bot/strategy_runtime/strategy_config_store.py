from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_bot.strategy_runtime.strategy_signal_schema import SUPPORTED_STRATEGIES, validate_strategy_id


DEFAULT_RUNTIME_CONFIG = {
    "active_strategy": "bb",
    "mode": "paper",
    "updated_by": "dashboard",
    "can_trade": False,
    "reason": "selector_read_only_stage",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_config_path(data_dir: Path) -> Path:
    return data_dir / "runtime_strategy_config.json"


def default_config() -> dict[str, Any]:
    return {**DEFAULT_RUNTIME_CONFIG, "updated_at": utc_now()}


def load_runtime_config(data_dir: Path, *, create: bool = True) -> dict[str, Any]:
    path = runtime_config_path(data_dir)
    if not path.exists():
        config = default_config()
        if create:
            save_runtime_config(data_dir, config)
        return config
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("runtime_strategy_config_not_object")
    strategy = validate_strategy_id(str(payload.get("active_strategy", "")))
    return {
        **DEFAULT_RUNTIME_CONFIG,
        **payload,
        "active_strategy": strategy,
        "can_trade": False,
        "reason": payload.get("reason") or "selector_read_only_stage",
    }


def save_runtime_config(data_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    path = runtime_config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **DEFAULT_RUNTIME_CONFIG,
        **config,
        "active_strategy": validate_strategy_id(str(config.get("active_strategy", ""))),
        "mode": str(config.get("mode") or "paper"),
        "updated_by": str(config.get("updated_by") or "dashboard"),
        "can_trade": False,
        "reason": str(config.get("reason") or "selector_read_only_stage"),
        "updated_at": config.get("updated_at") or utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _position_count_from_state(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"position_state_not_object:{path}")
    count = 0
    position = payload.get("position")
    if isinstance(position, dict):
        count += 1
    positions = payload.get("positions")
    if isinstance(positions, list):
        count += sum(1 for item in positions if isinstance(item, dict) and item.get("status", "open") != "closed")
    open_positions = payload.get("open_positions")
    if isinstance(open_positions, list):
        count += sum(1 for item in open_positions if isinstance(item, dict))
    if isinstance(open_positions, int):
        count += max(0, open_positions)
    return count


def read_position_state(data_dir: Path) -> dict[str, Any]:
    paths = [
        data_dir / "clean_paper_state.json",
        data_dir / "paper_state.json",
        data_dir / "paper_status.json",
    ]
    open_positions = 0
    existing = 0
    try:
        for path in paths:
            if path.exists():
                existing += 1
                open_positions += _position_count_from_state(path)
    except Exception as exc:
        return {
            "readable": False,
            "open_positions": 0,
            "reason": "position_state_unreadable",
            "error": str(exc),
        }
    return {
        "readable": True,
        "open_positions": open_positions,
        "reason": "position_state_read" if existing else "position_state_missing_assumed_flat",
        "files_checked": [str(path) for path in paths],
    }


def select_strategy(
    data_dir: Path,
    strategy: str,
    *,
    updated_by: str = "dashboard",
    position_reader: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        normalized = validate_strategy_id(strategy)
    except Exception:
        return {"status": "REJECTED", "reason": "unsupported_strategy", "supported_strategies": list(SUPPORTED_STRATEGIES)}
    reader = position_reader or read_position_state
    position_state = reader(data_dir)
    if not position_state.get("readable", False):
        return {
            "status": "BLOCKED",
            "reason": "position_state_unreadable_fail_closed",
            "position_state": position_state,
        }
    if int(position_state.get("open_positions", 0) or 0) > 0:
        return {
            "status": "BLOCKED",
            "reason": "open_position_strategy_switch_blocked",
            "position_state": position_state,
        }
    config = save_runtime_config(
        data_dir,
        {
            "active_strategy": normalized,
            "mode": "paper",
            "updated_by": updated_by,
            "can_trade": False,
            "reason": "selector_read_only_stage",
            "updated_at": utc_now(),
        },
    )
    return {
        "status": "OK",
        "reason": "strategy_selected_read_only",
        "config": config,
        "position_state": position_state,
    }
