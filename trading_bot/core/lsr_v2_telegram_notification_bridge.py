"""Prompt 29.4.4s-10ah — LSR-v2 Telegram notification bridge.

Read-only notification bridge for supervised LSR-v2 paper trade artifacts.

The bridge reads already-produced JSON/JSONL reports and optionally sends
Telegram notifications for:

* second paper order execution;
* second paper position close;
* second closed-trade final audit;
* two-trade postmortem;
* two-trade observation.

It never submits orders, never closes positions, never calls broker methods,
never mutates paper_state/paper_status, and never enables live/testnet/exchange
execution.  Actual Telegram sending is disabled by default and requires both an
explicit enable flag and confirmation phrase.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PROMPT_ID = "29.4.4s-10ah"
EVENT_TYPE = "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE"
REPORT_NAME = "lsr_v2_telegram_notification_bridge_report.json"
JSONL_NAME = "lsr_v2_telegram_notification_bridge.jsonl"
STATE_NAME = "lsr_v2_telegram_notification_bridge_state.json"

SEND_ENABLE_ENV = "LSR_V2_TELEGRAM_BRIDGE_ENABLE"
SEND_CONFIRM_ENV = "LSR_V2_TELEGRAM_BRIDGE_CONFIRMATION"
SEND_FORCE_ENV = "LSR_V2_TELEGRAM_BRIDGE_FORCE_RESEND"
MAX_MESSAGES_ENV = "LSR_V2_TELEGRAM_BRIDGE_MAX_MESSAGES"
REQUIRED_SEND_VALUE = "1"
REQUIRED_CONFIRMATION = "I_UNDERSTAND_SEND_LSR_V2_TELEGRAM_NOTIFICATIONS"

DRY_RUN_DECISION = "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_READY_DRY_RUN"
SENT_DECISION = "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_SENT"
PARTIAL_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_PARTIAL_SEND"
NOTHING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_NOTHING_TO_NOTIFY"
CONFIG_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_CONFIG_MISSING"
REJECT_DECISION = "REJECT_LSR_V2_TELEGRAM_BRIDGE_SAFETY_FAILED"

SECOND_SUBMIT_REPORT = "lsr_v2_second_trade_submit_execution_report.json"
SECOND_CLOSE_REPORT = "lsr_v2_second_trade_close_execution_report.json"
SECOND_FINAL_AUDIT_REPORT = "lsr_v2_second_closed_trade_final_audit_report.json"
TWO_TRADE_POSTMORTEM_REPORT = "lsr_v2_two_trade_paper_cycle_postmortem_report.json"
TWO_TRADE_OBSERVATION_REPORT = "lsr_v2_two_trade_observation_report.json"
TELEGRAM_AUDIT_NAME = "telegram_audit.jsonl"

Sender = Callable[[str], Mapping[str, Any] | bool | None]


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


def _fmt_num(value: Any, digits: int = 6) -> str:
    number = _safe_float(value, 0.0)
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


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


def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _load_state(path: str | Path) -> dict[str, Any]:
    state = _read_json(path)
    if not state:
        return {"sent_keys": []}
    if not isinstance(state.get("sent_keys"), list):
        state["sent_keys"] = []
    return state


def _state_sent_keys(state: Mapping[str, Any]) -> set[str]:
    raw = state.get("sent_keys")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x)}


def _update_state(path: str | Path, *, sent_keys: Iterable[str]) -> None:
    p = Path(path)
    state = _load_state(p)
    keys = sorted(_state_sent_keys(state).union({str(x) for x in sent_keys if str(x)}))
    state.update({"updated_at": utc_now_iso(), "sent_keys": keys})
    _write_json(p, state)


def _report_path(data_dir: str | Path, name: str) -> Path:
    return Path(data_dir) / name


@dataclass(frozen=True)
class LSRV2TelegramNotificationBridgeSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    state_name: str = STATE_NAME
    telegram_audit_name: str = TELEGRAM_AUDIT_NAME
    send_enable: str = ""
    send_confirmation: str = ""
    required_send_value: str = REQUIRED_SEND_VALUE
    required_send_confirmation: str = REQUIRED_CONFIRMATION
    force_resend: bool = False
    max_messages: int = 5
    telegram_token: str = ""
    telegram_chat_id: str = ""
    dry_run_prefix: str = "[LSR-v2 DRY-RUN]"
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2TelegramNotificationBridgeSettings":
        max_messages = _safe_int(os.getenv(MAX_MESSAGES_ENV), 5)
        if max_messages <= 0:
            max_messages = 5
        return cls(
            data_dir=data_dir,
            send_enable=str(os.getenv(SEND_ENABLE_ENV) or ""),
            send_confirmation=str(os.getenv(SEND_CONFIRM_ENV) or ""),
            force_resend=_safe_bool(os.getenv(SEND_FORCE_ENV), False),
            max_messages=max_messages,
            telegram_token=str(os.getenv("TELEGRAM_TOKEN") or ""),
            telegram_chat_id=str(os.getenv("TELEGRAM_CHAT_ID") or ""),
        )

    @property
    def send_enabled(self) -> bool:
        return str(self.send_enable).strip() == self.required_send_value

    @property
    def send_confirmation_ok(self) -> bool:
        return str(self.send_confirmation).strip() == self.required_send_confirmation

    @property
    def telegram_configured(self) -> bool:
        return bool(str(self.telegram_token).strip() and str(self.telegram_chat_id).strip())

    @property
    def actual_send_allowed(self) -> bool:
        return bool(self.send_enabled and self.send_confirmation_ok and self.telegram_configured and self.fail_closed)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if out.get("telegram_token"):
            out["telegram_token"] = "***"
        return out


@dataclass(frozen=True)
class LSRV2TelegramNotification:
    key: str
    kind: str
    title: str
    text: str
    source_report: str
    cycle_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_present(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _safe_decision(report: Mapping[str, Any]) -> str:
    return str(report.get("decision") or "")


def _report_pass(report: Mapping[str, Any], expected_decision: str = "") -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() != "PASS":
        return False
    if expected_decision:
        return _safe_decision(report) == expected_decision
    return True


def _order_message(report: Mapping[str, Any]) -> LSRV2TelegramNotification | None:
    if not _report_pass(report, "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED"):
        return None
    cycle_id = str(report.get("cycle_id") or "")
    symbol = str(_first_present(report.get("symbol"), (report.get("symbols") or [""])[0] if isinstance(report.get("symbols"), list) and report.get("symbols") else "", default="BTC/USDT"))
    side = str(_first_present(report.get("side"), (report.get("sides") or [""])[0] if isinstance(report.get("sides"), list) and report.get("sides") else "", default="BUY"))
    text = "\n".join([
        "🟢 LSR-v2 PAPER ORDER EXECUTED",
        f"trade=#2 cycle={cycle_id}",
        f"symbol={symbol} side={side}",
        f"notional={_fmt_num(report.get('total_notional'), 4)} risk={_fmt_num(report.get('total_risk_amount'), 4)}",
        "mode=paper-only | live=false | testnet=false | exchange=false",
    ])
    return LSRV2TelegramNotification(
        key=f"second_order_executed:{cycle_id}",
        kind="SECOND_ORDER_EXECUTED",
        title="LSR-v2 paper order executed",
        text=text,
        source_report=SECOND_SUBMIT_REPORT,
        cycle_id=cycle_id,
    )


def _close_message(report: Mapping[str, Any]) -> LSRV2TelegramNotification | None:
    if not _report_pass(report, "LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED"):
        return None
    cycle_id = str(report.get("cycle_id") or "")
    symbols = report.get("symbols") if isinstance(report.get("symbols"), list) else []
    sides = report.get("sides") if isinstance(report.get("sides"), list) else []
    reasons = report.get("close_reasons") if isinstance(report.get("close_reasons"), list) else []
    risk = _safe_float(report.get("total_risk_amount"), 0.0)
    pnl = _safe_float(report.get("realized_pnl_total"), 0.0)
    r_mult = pnl / risk if risk > 0 else 0.0
    text = "\n".join([
        "✅ LSR-v2 PAPER POSITION CLOSED",
        f"trade=#2 cycle={cycle_id}",
        f"symbol={(symbols or ['BTC/USDT'])[0]} side={(sides or ['BUY'])[0]}",
        f"reason={(reasons or [''])[0]}",
        f"realized_pnl={_fmt_num(pnl, 6)} R={_fmt_num(r_mult, 6)}",
        "position_after=0 | no_reentry=true",
    ])
    return LSRV2TelegramNotification(
        key=f"second_position_closed:{cycle_id}",
        kind="SECOND_POSITION_CLOSED",
        title="LSR-v2 paper position closed",
        text=text,
        source_report=SECOND_CLOSE_REPORT,
        cycle_id=cycle_id,
    )


def _second_final_message(report: Mapping[str, Any]) -> LSRV2TelegramNotification | None:
    if not _report_pass(report, "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS"):
        return None
    cycle_id = str(report.get("cycle_id") or "")
    text = "\n".join([
        "📋 LSR-v2 SECOND TRADE FINAL AUDIT PASS",
        f"cycle={cycle_id}",
        f"realized_pnl={_fmt_num(report.get('realized_pnl_total'), 6)} R={_fmt_num(report.get('realized_r'), 6)}",
        f"residual_open_position={str(report.get('residual_open_position')).lower()}",
        f"third_trade_allowed={str(report.get('third_trade_allowed')).lower()}",
    ])
    return LSRV2TelegramNotification(
        key=f"second_final_audit:{cycle_id}",
        kind="SECOND_FINAL_AUDIT_PASS",
        title="LSR-v2 second final audit pass",
        text=text,
        source_report=SECOND_FINAL_AUDIT_REPORT,
        cycle_id=cycle_id,
    )


def _postmortem_message(report: Mapping[str, Any]) -> LSRV2TelegramNotification | None:
    if not _report_pass(report, "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS"):
        return None
    cycle_ids = report.get("cycle_ids") if isinstance(report.get("cycle_ids"), list) else []
    key_suffix = "+".join(str(x) for x in cycle_ids) or "two_trade"
    text = "\n".join([
        "📊 LSR-v2 TWO-TRADE POSTMORTEM PASS",
        f"cycles={','.join(str(x) for x in cycle_ids)}",
        f"total_pnl={_fmt_num(report.get('total_realized_pnl'), 6)} avg_R={_fmt_num(report.get('average_realized_r'), 6)}",
        f"submit_events={_safe_int(report.get('submit_execution_events_total'), 0)} close_events={_safe_int(report.get('close_execution_events_total'), 0)}",
        f"third_trade_locked={str(report.get('third_trade_locked')).lower()}",
    ])
    return LSRV2TelegramNotification(
        key=f"two_trade_postmortem:{key_suffix}",
        kind="TWO_TRADE_POSTMORTEM_PASS",
        title="LSR-v2 two-trade postmortem pass",
        text=text,
        source_report=TWO_TRADE_POSTMORTEM_REPORT,
        cycle_id=key_suffix,
    )


def _observation_message(report: Mapping[str, Any]) -> LSRV2TelegramNotification | None:
    if not _report_pass(report, "LSR_V2_TWO_TRADE_OBSERVATION_PASS"):
        return None
    cycles = _safe_int(report.get("completed_observation_cycles"), 0)
    cycle_ids = report.get("cycle_ids") if isinstance(report.get("cycle_ids"), list) else []
    key_suffix = "+".join(str(x) for x in cycle_ids) or "two_trade"
    text = "\n".join([
        "🔒 LSR-v2 TWO-TRADE OBSERVATION PASS",
        f"completed_cycles={cycles} failed={_safe_int(report.get('failed_observation_cycles'), 0)} timeouts={_safe_int(report.get('timed_out_cycles'), 0)}",
        f"new_submit_cycles={report.get('new_submit_cycles') or []}",
        f"open_positions={_safe_int(report.get('paper_status_open_positions'), 0)} pending_orders={_safe_int(report.get('paper_status_pending_orders'), 0)}",
        f"third_trade_locked={str(report.get('third_trade_locked')).lower()}",
    ])
    return LSRV2TelegramNotification(
        key=f"two_trade_observation:{key_suffix}:cycles:{cycles}",
        kind="TWO_TRADE_OBSERVATION_PASS",
        title="LSR-v2 two-trade observation pass",
        text=text,
        source_report=TWO_TRADE_OBSERVATION_REPORT,
        cycle_id=key_suffix,
    )


def build_lsr_v2_telegram_notifications(data_dir: str | Path) -> tuple[list[LSRV2TelegramNotification], dict[str, Any]]:
    base = Path(data_dir)
    reports = {
        SECOND_SUBMIT_REPORT: _read_json(base / SECOND_SUBMIT_REPORT),
        SECOND_CLOSE_REPORT: _read_json(base / SECOND_CLOSE_REPORT),
        SECOND_FINAL_AUDIT_REPORT: _read_json(base / SECOND_FINAL_AUDIT_REPORT),
        TWO_TRADE_POSTMORTEM_REPORT: _read_json(base / TWO_TRADE_POSTMORTEM_REPORT),
        TWO_TRADE_OBSERVATION_REPORT: _read_json(base / TWO_TRADE_OBSERVATION_REPORT),
    }
    builders = [
        _order_message(reports[SECOND_SUBMIT_REPORT]),
        _close_message(reports[SECOND_CLOSE_REPORT]),
        _second_final_message(reports[SECOND_FINAL_AUDIT_REPORT]),
        _postmortem_message(reports[TWO_TRADE_POSTMORTEM_REPORT]),
        _observation_message(reports[TWO_TRADE_OBSERVATION_REPORT]),
    ]
    notifications = [n for n in builders if n is not None]
    diagnostics = {
        "source_reports": {
            name: {
                "present": bool(payload),
                "status": str(payload.get("status") or "") if payload else "",
                "decision": str(payload.get("decision") or "") if payload else "",
            }
            for name, payload in reports.items()
        },
        "notification_candidate_count": len(notifications),
    }
    return notifications, diagnostics


def send_telegram_text_via_http(*, token: str, chat_id: str, text: str) -> dict[str, Any]:
    if not token or not chat_id:
        return {"ok": False, "error": "telegram_config_missing"}
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe='')}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:3900]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - operator configured Telegram endpoint
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return {"ok": bool(parsed.get("ok", False)), "response": parsed}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}


def _default_sender(settings: LSRV2TelegramNotificationBridgeSettings) -> Sender:
    def sender(text: str) -> Mapping[str, Any]:
        return send_telegram_text_via_http(token=settings.telegram_token, chat_id=settings.telegram_chat_id, text=text)
    return sender


def run_lsr_v2_telegram_notification_bridge(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2TelegramNotificationBridgeSettings | None = None,
    sender: Sender | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2TelegramNotificationBridgeSettings.from_env(data_dir=str(data_dir))
    base = Path(data_dir)
    notifications, diagnostics = build_lsr_v2_telegram_notifications(data_dir)
    state_path = base / settings.state_name
    state = _load_state(state_path)
    sent_before = _state_sent_keys(state)

    selected: list[LSRV2TelegramNotification] = []
    skipped_duplicates: list[str] = []
    for item in notifications:
        if item.key in sent_before and not settings.force_resend:
            skipped_duplicates.append(item.key)
            continue
        selected.append(item)
    selected = selected[: max(0, settings.max_messages)]

    events: list[dict[str, Any]] = []
    sent_keys: list[str] = []
    failed_count = 0
    send_attempted = False
    actual_sender = sender or _default_sender(settings)

    safety_violation = False
    if not settings.fail_closed:
        safety_violation = True

    for notification in selected:
        base_event = {
            "event_type": EVENT_TYPE,
            "prompt_id": PROMPT_ID,
            "created_at": utc_now_iso(),
            "notification_key": notification.key,
            "notification_kind": notification.kind,
            "source_report": notification.source_report,
            "cycle_id": notification.cycle_id,
            "message_preview": notification.text[:500],
            "send_enabled": bool(settings.send_enabled),
            "send_confirmation_ok": bool(settings.send_confirmation_ok),
            "telegram_configured": bool(settings.telegram_configured),
            "actual_send_allowed": bool(settings.actual_send_allowed),
            "broker_submit_called_by_telegram_bridge": False,
            "broker_close_called_by_telegram_bridge": False,
            "orders_submitted_by_telegram_bridge": 0,
            "positions_opened_by_telegram_bridge": 0,
            "positions_closed_by_telegram_bridge": 0,
            "paper_state_modified_by_telegram_bridge": False,
            "paper_status_modified_by_telegram_bridge": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "operational_unlock_allowed": False,
            "promotion_ready": False,
        }
        if settings.actual_send_allowed:
            send_attempted = True
            result = actual_sender(notification.text)
            result_map = result if isinstance(result, Mapping) else {"ok": bool(result)}
            ok = _safe_bool(result_map.get("ok"), False)
            if ok:
                sent_keys.append(notification.key)
            else:
                failed_count += 1
            event = {**base_event, "telegram_send_attempted": True, "telegram_send_ok": ok, "telegram_send_result": dict(result_map)}
        else:
            event = {**base_event, "telegram_send_attempted": False, "telegram_send_ok": False, "telegram_send_result": {}, "dry_run": True}
        events.append(event)

    _write_jsonl_replace(base / settings.jsonl_name, events)
    for event in events:
        _append_jsonl(base / settings.telegram_audit_name, {
            "ts": utc_now_iso(),
            "event_type": "LSR_V2_TELEGRAM_BRIDGE_AUDIT",
            "notification_key": event.get("notification_key"),
            "notification_kind": event.get("notification_kind"),
            "telegram_send_attempted": event.get("telegram_send_attempted"),
            "telegram_send_ok": event.get("telegram_send_ok"),
            "dry_run": event.get("dry_run", False),
        })
    if sent_keys:
        _update_state(state_path, sent_keys=sent_keys)

    blockers: list[str] = []
    if safety_violation:
        blockers.append("fail_closed_disabled")
    if settings.send_enabled and not settings.send_confirmation_ok:
        blockers.append("telegram_bridge_confirmation_missing")
    if settings.send_enabled and settings.send_confirmation_ok and not settings.telegram_configured:
        blockers.append("telegram_config_missing")
    if failed_count > 0:
        blockers.append("telegram_send_failed")

    if safety_violation:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not notifications:
        decision = NOTHING_DECISION
        status = "WARN"
    elif settings.send_enabled and settings.send_confirmation_ok and not settings.telegram_configured:
        decision = CONFIG_MISSING_DECISION
        status = "WARN"
    elif settings.actual_send_allowed and failed_count == 0 and send_attempted:
        decision = SENT_DECISION
        status = "PASS"
    elif settings.actual_send_allowed and failed_count > 0:
        decision = PARTIAL_DECISION
        status = "WARN"
    else:
        decision = DRY_RUN_DECISION
        status = "PASS"

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_TELEGRAM_BRIDGE",
            "OBSERVABILITY_ONLY",
            "NO_TRADING_SIDE_EFFECTS",
        ] + (["TELEGRAM_SENT"] if decision == SENT_DECISION else ["TELEGRAM_DRY_RUN"]),
        "blockers": sorted(set(blockers)),
        "settings": settings.to_dict(),
        "send_enabled": bool(settings.send_enabled),
        "send_confirmation_ok": bool(settings.send_confirmation_ok),
        "telegram_configured": bool(settings.telegram_configured),
        "actual_send_allowed": bool(settings.actual_send_allowed),
        "force_resend": bool(settings.force_resend),
        "max_messages": int(settings.max_messages),
        "notification_candidate_count": len(notifications),
        "notification_selected_count": len(selected),
        "notification_duplicate_skipped_count": len(skipped_duplicates),
        "notification_duplicate_skipped_keys": skipped_duplicates,
        "telegram_send_attempted_count": sum(1 for e in events if _safe_bool(e.get("telegram_send_attempted"), False)),
        "telegram_send_ok_count": sum(1 for e in events if _safe_bool(e.get("telegram_send_ok"), False)),
        "telegram_send_failed_count": failed_count,
        "notification_kinds": [n.kind for n in selected],
        "notification_keys": [n.key for n in selected],
        "source_report_diagnostics": diagnostics["source_reports"],
        "broker_submit_called_by_telegram_bridge": False,
        "broker_close_called_by_telegram_bridge": False,
        "orders_submitted_by_telegram_bridge": 0,
        "positions_opened_by_telegram_bridge": 0,
        "positions_closed_by_telegram_bridge": 0,
        "paper_state_modified_by_telegram_bridge": False,
        "paper_status_modified_by_telegram_bridge": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
        "state_path": str(base / settings.state_name),
        "telegram_audit_path": str(base / settings.telegram_audit_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
