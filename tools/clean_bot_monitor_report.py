from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        try:
            import pandas as pd

            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:
            return None


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return max(0.0, (_utc_now() - parsed).total_seconds())


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_jsonl_tail(path: Path, tail: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if tail > 0:
        lines = lines[-tail:]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def _filter_since(events: list[dict[str, Any]], since_minutes: float) -> list[dict[str, Any]]:
    if since_minutes <= 0:
        return events
    cutoff = _utc_now().timestamp() - since_minutes * 60.0
    filtered: list[dict[str, Any]] = []
    for event in events:
        parsed = _parse_ts(event.get("ts"))
        if parsed is not None and parsed.timestamp() >= cutoff:
            filtered.append(event)
    return filtered


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _telegram_env_status() -> dict[str, Any]:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    placeholder = token == "IL_TUO_TOKEN" or chat_id == "IL_TUO_CHAT_ID"
    return {
        "token_present": bool(token),
        "chat_id_present": bool(chat_id),
        "placeholder_values": placeholder,
        "ready": bool(token and chat_id and not placeholder),
    }


def _send_telegram(text: str) -> dict[str, Any]:
    env = _telegram_env_status()
    if not env["token_present"] or not env["chat_id_present"]:
        return {"ok": False, "reason": "missing_TELEGRAM_TOKEN_or_TELEGRAM_CHAT_ID"}
    if env["placeholder_values"]:
        return {"ok": False, "reason": "placeholder_telegram_values"}
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"ok": 200 <= int(response.status) < 300, "status": int(response.status)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "reason": "telegram_http_error", "status": int(exc.code), "body": body}
    except Exception as exc:
        return {"ok": False, "reason": "telegram_send_error", "error": str(exc)}


def _last_event(events: list[dict[str, Any]], event_type: str | None = None) -> dict[str, Any]:
    for event in reversed(events):
        if event_type is None or event.get("event_type") == event_type:
            return event
    return {}


def _action_counts(events: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events:
        action = event.get("action")
        if action:
            counts[str(action)] += 1
    return counts


def _equity_stats(events: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    values = [_f(event.get("equity")) for event in events if event.get("equity") is not None]
    initial = _f(state.get("initial_balance"), 100.0)
    current = values[-1] if values else _f(state.get("cash"), initial)
    return {
        "initial_balance": initial,
        "current_equity": current,
        "equity_change": current - initial,
        "equity_change_pct": (current - initial) / initial * 100.0 if initial else 0.0,
        "min_equity": min(values) if values else current,
        "max_equity": max(values) if values else current,
        "realized_pnl": _f(state.get("realized_pnl")),
    }


def _position_summary(state: dict[str, Any]) -> dict[str, Any]:
    position = state.get("position")
    if not isinstance(position, dict):
        return {"open": False}
    return {
        "open": True,
        "symbol": position.get("symbol"),
        "side": position.get("side"),
        "strategy": position.get("strategy"),
        "opened_bar": position.get("opened_bar"),
        "entry_price": _f(position.get("entry_price")),
        "qty": _f(position.get("qty")),
        "stop_loss": _f(position.get("stop_loss")),
        "take_profit": _f(position.get("take_profit")),
        "signal_reason": position.get("signal_reason", ""),
    }


def _health(report: dict[str, Any], expected_poll_seconds: float) -> list[str]:
    health: list[str] = []
    if not report["paths"]["state_exists"]:
        health.append("NO_CLEAN_STATE_YET")
    if not report["paths"]["events_exists"]:
        health.append("NO_CLEAN_EVENTS_YET")
    age = report["runtime"].get("last_event_age_seconds")
    if age is None:
        health.append("NO_RECENT_EVENT")
    elif age > max(600.0, expected_poll_seconds * 5.0):
        health.append("BOT_MAY_BE_STOPPED_OR_NOT_WRITING_EVENTS")
    elif age <= max(180.0, expected_poll_seconds * 3.0):
        health.append("EVENT_STREAM_RECENT")

    counts = report["events"]["action_counts"]
    completed = counts.get("HOLD", 0) + counts.get("OPEN", 0) + counts.get("CLOSE", 0) + counts.get("TRAIL_UPDATE", 0)
    skipped = counts.get("SKIP_STALE_OR_DUPLICATE_BAR", 0)
    total_cycles = completed + skipped
    if total_cycles and skipped / total_cycles >= 0.70:
        health.append("MANY_DUPLICATE_BAR_SKIPS_EXPECTED_IF_POLL_LT_TIMEFRAME")
    if report["trades"]["opened_events"] == 0 and report["trades"]["state_closed_trades"] == 0:
        health.append("NO_PAPER_TRADES_RECORDED_YET")
    if report["signals"]["signals_seen"] == 0 and completed:
        health.append("NO_SIGNALS_IN_ANALYZED_WINDOW")
    if report["telegram"]["ready"]:
        health.append("TELEGRAM_ENV_READY_IN_THIS_TERMINAL")
    else:
        health.append("TELEGRAM_ENV_NOT_READY_IN_THIS_TERMINAL")
    return health


def build_report(*, data_dir: Path, tail: int = 2000, since_minutes: float = 0.0, expected_poll_seconds: float = 60.0) -> dict[str, Any]:
    state_path = data_dir / "clean_paper_state.json"
    events_path = data_dir / "clean_paper_events.jsonl"
    state = _read_json(state_path)
    raw_events = _read_jsonl_tail(events_path, tail)
    events = _filter_since(raw_events, since_minutes)
    event_types = Counter(str(event.get("event_type", "UNKNOWN")) for event in events)
    actions = _action_counts(events)
    sources = Counter(str(event.get("source", "UNKNOWN")) for event in events if event.get("source"))
    last_any = _last_event(events)
    last_completed = _last_event(events, "CLEAN_CYCLE_COMPLETED")
    last_skipped = _last_event(events, "CLEAN_CYCLE_SKIPPED")

    signal_events = [event for event in events if isinstance(event.get("signal"), dict)]
    no_signal_completed = [
        event
        for event in events
        if event.get("event_type") == "CLEAN_CYCLE_COMPLETED" and event.get("signal") in {None, ""}
    ]
    signal_reasons = Counter()
    for event in signal_events:
        signal = event.get("signal")
        if isinstance(signal, dict):
            signal_reasons[str(signal.get("reason") or "unknown")] += 1

    opened_events = [event for event in events if event.get("event_type") == "CLEAN_POSITION_OPENED"]
    closed_events = [event for event in events if event.get("event_type") == "CLEAN_POSITION_CLOSED"]
    closed_state = state.get("closed_trades") if isinstance(state.get("closed_trades"), list) else []
    report: dict[str, Any] = {
        "report_type": "clean_bot_monitor_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "generated_at": _utc_now().isoformat(),
        "paths": {
            "state": str(state_path),
            "events": str(events_path),
            "state_exists": state_path.exists(),
            "events_exists": events_path.exists(),
        },
        "settings": {
            "tail": tail,
            "since_minutes": since_minutes,
            "expected_poll_seconds": expected_poll_seconds,
        },
        "state": {
            "symbol": state.get("symbol", ""),
            "timeframe": state.get("timeframe", ""),
            "profile": state.get("profile", ""),
            "updated_at": state.get("updated_at", ""),
            "updated_age_seconds": _age_seconds(state.get("updated_at")),
            "last_processed_bar": state.get("last_processed_bar", ""),
            "last_processed_bar_age_seconds": _age_seconds(state.get("last_processed_bar")),
            "cash": _f(state.get("cash")),
            "realized_pnl": _f(state.get("realized_pnl")),
        },
        "runtime": {
            "events_loaded": len(raw_events),
            "events_analyzed": len(events),
            "last_event_ts": last_any.get("ts", ""),
            "last_event_age_seconds": _age_seconds(last_any.get("ts")),
            "last_event_type": last_any.get("event_type", ""),
            "last_action": last_any.get("action", ""),
            "last_cycle_bar": (last_completed or last_skipped).get("bar_time", ""),
            "last_cycle_source": (last_completed or last_skipped).get("source", ""),
        },
        "events": {
            "event_type_counts": dict(event_types),
            "action_counts": dict(actions),
            "source_counts": dict(sources),
        },
        "signals": {
            "signals_seen": len(signal_events),
            "no_signal_completed_cycles": len(no_signal_completed),
            "signal_reasons": dict(signal_reasons),
        },
        "trades": {
            "opened_events": len(opened_events),
            "closed_events": len(closed_events),
            "state_closed_trades": len(closed_state),
            "last_open_event_ts": _last_event(events, "CLEAN_POSITION_OPENED").get("ts", ""),
            "last_close_event_ts": _last_event(events, "CLEAN_POSITION_CLOSED").get("ts", ""),
        },
        "equity": _equity_stats(events, state),
        "position": _position_summary(state),
        "telegram": _telegram_env_status(),
    }
    report["health"] = _health(report, expected_poll_seconds)
    return report


def _fmt_age(seconds: Any) -> str:
    if seconds is None:
        return "unknown"
    seconds = _f(seconds)
    if seconds < 90:
        return f"{seconds:.0f}s"
    minutes = seconds / 60.0
    if minutes < 120:
        return f"{minutes:.1f}m"
    return f"{minutes / 60.0:.1f}h"


def _fmt_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def format_report(report: dict[str, Any]) -> str:
    state = report["state"]
    runtime = report["runtime"]
    equity = report["equity"]
    position = report["position"]
    lines = [
        "CLEAN PAPER MONITOR",
        f"symbol={state.get('symbol') or '-'} timeframe={state.get('timeframe') or '-'} profile={state.get('profile') or '-'}",
        f"last_event={runtime.get('last_event_type') or '-'} action={runtime.get('last_action') or '-'} age={_fmt_age(runtime.get('last_event_age_seconds'))}",
        f"last_bar={runtime.get('last_cycle_bar') or '-'} source={runtime.get('last_cycle_source') or '-'}",
        f"equity={equity['current_equity']:.2f} change={equity['equity_change']:+.2f} ({equity['equity_change_pct']:+.2f}%) realized={equity['realized_pnl']:+.2f}",
        f"position_open={'YES' if position.get('open') else 'NO'} closed_trades={report['trades']['state_closed_trades']} opened_events={report['trades']['opened_events']} closed_events={report['trades']['closed_events']}",
        f"actions={_fmt_counts(report['events']['action_counts'])}",
        f"signals_seen={report['signals']['signals_seen']} no_signal_cycles={report['signals']['no_signal_completed_cycles']}",
        f"telegram_ready={'YES' if report['telegram']['ready'] else 'NO'}",
        "health=" + ", ".join(report["health"]),
    ]
    if position.get("open"):
        lines.extend(
            [
                f"open_entry={position['entry_price']:.6f} qty={position['qty']:.6f} stop={position['stop_loss']:.6f}",
                f"open_reason={position.get('signal_reason') or '-'}",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report clean paper bot health from state/events.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tail", type=int, default=2000)
    parser.add_argument("--since-minutes", type=float, default=0.0)
    parser.add_argument("--expected-poll-seconds", type=float, default=60.0)
    parser.add_argument("--output", default="data/clean_bot_monitor_report.json")
    parser.add_argument("--telegram", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(
        data_dir=Path(args.data_dir),
        tail=args.tail,
        since_minutes=args.since_minutes,
        expected_poll_seconds=args.expected_poll_seconds,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    text = format_report(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(text)
        print(f"report={args.output}")
    if args.telegram:
        result = _send_telegram(text)
        print(f"TELEGRAM_MONITOR ok={result.get('ok')} reason={result.get('reason', '')} status={result.get('status', '')}")
        if result.get("body"):
            print(f"telegram_body={result.get('body')}")
        if result.get("error"):
            print(f"telegram_error={result.get('error')}")
        return 0 if result.get("ok") else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
