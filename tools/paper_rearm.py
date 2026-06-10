from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIRM_PHRASE = "I_UNDERSTAND_REARM_PAPER_ONLY"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _open_positions(state: dict[str, Any]) -> int:
    positions = state.get("positions")
    rows = positions.values() if isinstance(positions, dict) else positions if isinstance(positions, list) else []
    return sum(1 for p in rows if isinstance(p, dict) and str(p.get("status") or "").upper() == "OPEN")


def rearm_paper(data_dir: Path, *, confirm: str, dry_run: bool = False) -> dict[str, Any]:
    if confirm != CONFIRM_PHRASE:
        return {"status": "BLOCKED", "reason": "confirmation_missing", "required_confirmation": CONFIRM_PHRASE}
    state_path = data_dir / "paper_state.json"
    status_path = data_dir / "paper_status.json"
    events_path = data_dir / "paper_events.jsonl"
    state = _read_json(state_path)
    status = _read_json(status_path)
    open_positions = _open_positions(state)
    if open_positions:
        return {"status": "BLOCKED", "reason": "open_positions_present", "open_positions": open_positions}
    now = datetime.now(timezone.utc).isoformat()
    before = {
        "state_kill_switch": bool(state.get("kill_switch")),
        "state_is_paused": bool(state.get("is_paused")),
        "status_kill_switch": bool(status.get("kill_switch")),
        "status_is_paused": bool(status.get("is_paused")),
    }
    if dry_run:
        return {"status": "DRY_RUN", "before": before, "open_positions": 0}
    backup_dir = data_dir / "paper_rearm_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.replace(":", "").replace("-", "").replace(".", "_")
    if state_path.exists():
        shutil.copy2(state_path, backup_dir / f"paper_state_{stamp}.json")
    if status_path.exists():
        shutil.copy2(status_path, backup_dir / f"paper_status_{stamp}.json")
    state["kill_switch"] = False
    state["is_paused"] = False
    state["rearmed_at"] = now
    state["rearm_reason"] = "PAPER_ONLY_OPERATOR_REARM"
    status["kill_switch"] = False
    status["is_paused"] = False
    status["updated_at"] = now
    status["paper_rearmed_at"] = now
    _write_json(state_path, state)
    _write_json(status_path, status)
    event = {
        "event_type": "PAPER_ONLY_REARMED",
        "ts": now,
        "reason": "PAPER_ONLY_OPERATOR_REARM",
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "before": before,
        "after": {"kill_switch": False, "is_paused": False},
    }
    _append_event(events_path, event)
    return {"status": "PASS", "event": event, "backup_dir": str(backup_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rearm paper-only trading after an operator kill switch.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = rearm_paper(Path(args.data_dir), confirm=str(args.confirm), dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"PASS", "DRY_RUN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
