"""Prompt 29.4.4o-2 paper once-cycle console flush hotfix.

This module is deliberately formatting-only. It reads already-produced cycle and
runtime audit summaries and prints a clear terminal footer for ``--once`` runs.
It never changes gates, routing, risk, broker state, orders, or positions.

29.4.4o-2 only hardens console delivery: every footer line is flushed and the
caller can use the printed flag/fallback guard to avoid missing stdout footers.
"""
from __future__ import annotations

import sys
from typing import Any, Mapping, TextIO

PROMPT_ID = "29.4.4o-3c"
READY_DECISION = "PAPER_ONCE_CONSOLE_SUMMARY_FLUSH_READY"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        return float(value)
    except Exception:
        return default


def _bool_label(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"unknown", "", "none", "null"}:
            return "unknown"
        if lowered in {"true", "1", "yes", "on"}:
            return "true"
        if lowered in {"false", "0", "no", "off"}:
            return "false"
    if value is None:
        return "unknown"
    return "true" if bool(value) else "false"


def build_paper_once_console_summary_lines(
    summary: Mapping[str, Any],
    *,
    runtime_audit: Mapping[str, Any] | None = None,
    routing_bridge: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deterministic console lines for a completed ``--once`` cycle.

    The function is pure and non-invasive: callers supply the already-computed
    cycle summary and optional audit reports; no file system or broker writes are
    performed here.
    """
    summary = summary if isinstance(summary, Mapping) else {}
    runtime_audit = runtime_audit if isinstance(runtime_audit, Mapping) else {}
    routing_bridge = routing_bridge if isinstance(routing_bridge, Mapping) else {}
    runtime_decision = _safe_dict(runtime_audit.get("decision"))
    bridge_decision = _safe_dict(routing_bridge.get("decision"))

    scanned = _safe_int(summary.get("scanned"), 0)
    signals = _safe_int(summary.get("signals"), 0)
    orders = _safe_int(summary.get("orders"), 0)
    open_positions = _safe_int(summary.get("open_positions"), 0)
    errors = _safe_int(summary.get("errors"), 0)
    no_signal = _safe_int(summary.get("no_signal"), 0)

    paper_orders_enabled = runtime_audit.get("paper_orders_enabled")
    if paper_orders_enabled is None:
        paper_orders_enabled = routing_bridge.get("paper_orders_enabled", False)
    paper_unlock_experiment_allowed = runtime_audit.get("paper_unlock_experiment_allowed")
    if paper_unlock_experiment_allowed is None:
        paper_unlock_experiment_allowed = routing_bridge.get("paper_unlock_experiment_allowed", False)
    operational_unlock_allowed = runtime_audit.get("operational_unlock_allowed")
    if operational_unlock_allowed is None:
        operational_unlock_allowed = routing_bridge.get("operational_unlock_allowed", False)

    prompt_val = summary.get("prompt") or PROMPT_ID

    lines = [
        "[PAPER CYCLE COMPLETED]",
        f"cycle_id={summary.get('cycle_id') or ''}",
        f"scanned={scanned}",
        f"signals={signals}",
        f"orders={orders}",
        f"open_positions={open_positions}",
        f"errors={errors}",
        f"elapsed_seconds={_safe_float(summary.get('elapsed_seconds'), 0.0):.4f}",
        f"paper_orders_enabled={_bool_label(paper_orders_enabled)}",
        f"paper_unlock_experiment_allowed={_bool_label(paper_unlock_experiment_allowed)}",
        f"manual_activation_allowed={_bool_label(summary.get('manual_activation_allowed', runtime_audit.get('manual_activation_allowed', routing_bridge.get('manual_activation_allowed'))))}",
        f"operational_unlock_allowed={_bool_label(operational_unlock_allowed)}",
        f"live_allowed={_bool_label(summary.get('live_allowed', runtime_audit.get('live_allowed', routing_bridge.get('live_allowed', False))))}",
        f"testnet_allowed={_bool_label(summary.get('testnet_allowed', runtime_audit.get('testnet_allowed', routing_bridge.get('testnet_allowed', False))))}",
        f"exchange_broker_allowed={_bool_label(summary.get('exchange_broker_allowed', runtime_audit.get('exchange_broker_allowed', routing_bridge.get('exchange_broker_allowed', False))))}",
        f"runtime_audit_events={_safe_int(runtime_decision.get('runtime_audit_events'), 0)}",
        f"runtime_accepts_diagnostic={_safe_int(runtime_decision.get('runtime_accepts_diagnostic'), 0)}",
        f"runtime_rejects={_safe_int(runtime_decision.get('runtime_rejects'), 0)}",
    ]

    if prompt_val:
        lines.append(f"prompt={prompt_val}")
    if "footer_source" in summary:
        lines.append(f"footer_source={summary['footer_source']}")

    if routing_bridge:
        lines.extend([
            f"routing_bridge_events={_safe_int(bridge_decision.get('routing_bridge_events'), 0)}",
            f"would_route_count={_safe_int(bridge_decision.get('would_route_count'), 0)}",
            f"would_submit_count={_safe_int(bridge_decision.get('would_submit_count'), 0)}",
            f"orders_submitted_by_bridge={_safe_int(bridge_decision.get('orders_submitted_by_bridge'), 0)}",
            f"positions_opened_by_bridge={_safe_int(bridge_decision.get('positions_opened_by_bridge'), 0)}",
        ])

    if signals == 0 and orders == 0:
        reason = "all assets rejected by filters"
        if scanned <= 0:
            reason = "no assets scanned"
        elif no_signal < scanned and errors > 0:
            reason = "no qualifying signals; one or more assets errored"
        lines.extend([
            "[PAPER ONCE RESULT] NO_SIGNAL",
            f"scanned={scanned}",
            f"orders={orders}",
            f"positions={open_positions}",
            f"reason={reason}",
        ])
    elif orders == 0:
        lines.extend([
            "[PAPER ONCE RESULT] SIGNAL_NO_ORDER",
            f"signals={signals}",
            f"orders={orders}",
            f"positions={open_positions}",
            "reason=signal detected but order path did not submit",
        ])
    else:
        lines.extend([
            "[PAPER ONCE RESULT] ORDER_SUBMITTED",
            f"signals={signals}",
            f"orders={orders}",
            f"positions={open_positions}",
        ])

    return lines


def print_paper_once_console_summary(
    summary: Mapping[str, Any],
    *,
    runtime_audit: Mapping[str, Any] | None = None,
    routing_bridge: Mapping[str, Any] | None = None,
    stream: TextIO | None = None,
    flush: bool = True,
) -> None:
    """Print the once-cycle footer and force stdout delivery.

    The function remains formatting-only. ``flush=True`` is intentional for the
    Windows operator console case where the JSONL cycle has been written but the
    terminal footer can be missed before process shutdown or interruption.
    """
    target = stream if stream is not None else sys.stdout
    for line in build_paper_once_console_summary_lines(summary, runtime_audit=runtime_audit, routing_bridge=routing_bridge):
        print(line, file=target, flush=flush)
    if flush:
        try:
            target.flush()
        except Exception:
            pass
