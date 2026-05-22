"""Backtest lifecycle consistency utilities.

This module is intentionally dependency-light so it can be tested without loading
exchange clients, technical indicators or ML dependencies.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable


def canonical_trade_pnl(trade: Dict[str, Any]) -> float:
    """Return realized PnL from legacy or canonical trade dictionaries."""
    for key in ("realized_pnl", "pnl", "pnl_amount", "pnl_eur", "profit"):
        if key in trade and trade[key] is not None:
            try:
                return float(trade[key])
            except (TypeError, ValueError):
                continue
    return 0.0


def count_visualized_trades(charts_dir: str) -> int:
    if not charts_dir or not os.path.isdir(charts_dir):
        return 0
    return len([name for name in os.listdir(charts_dir) if name.endswith(".html")])


def build_lifecycle_report(
    *,
    trades: Iterable[Dict[str, Any]],
    risk_events: int,
    risk_bearing_snapshots: int,
    visualized_trades: int = 0,
    charting_enabled: bool = True,
) -> Dict[str, Any]:
    trades = list(trades)
    closed_trades = len(trades)
    balance_mutation_mismatches = 0

    for trade in trades:
        expected_after = float(trade.get("balance_before", trade.get("balance", 0.0))) + canonical_trade_pnl(trade)
        actual_after = float(trade.get("balance_after", trade.get("balance", 0.0)))
        if abs(expected_after - actual_after) > 1e-6:
            balance_mutation_mismatches += 1

    closed_equals_risk_events = closed_trades == int(risk_events or 0)
    closed_equals_risk_bearing = closed_trades == int(risk_bearing_snapshots or 0)
    charting_enabled = bool(charting_enabled)
    closed_equals_visualized_raw = visualized_trades == closed_trades
    # In fast / no-charts research mode chart generation is intentionally disabled.
    # Missing HTML files must not downgrade lifecycle consistency: trade/risk/balance
    # invariants are the authoritative checks in that mode.
    closed_equals_visualized = (not charting_enabled) or visualized_trades == 0 or closed_equals_visualized_raw
    visualization_mismatch_ignored_due_to_no_charts = (
        not charting_enabled and int(visualized_trades or 0) != int(closed_trades or 0)
    )
    status = "PASS" if (
        closed_equals_risk_events
        and closed_equals_risk_bearing
        and closed_equals_visualized
        and balance_mutation_mismatches == 0
    ) else "WARN"

    return {
        "closed_trades": closed_trades,
        "risk_events": int(risk_events or 0),
        "risk_bearing_snapshots": int(risk_bearing_snapshots or 0),
        "visualized_trades": int(visualized_trades or 0),
        "balance_mutation_mismatches": balance_mutation_mismatches,
        "closed_equals_risk_events": closed_equals_risk_events,
        "closed_equals_risk_bearing_snapshots": closed_equals_risk_bearing,
        "charting_enabled": charting_enabled,
        "closed_equals_visualized_raw": closed_equals_visualized_raw,
        "closed_equals_visualized_when_enabled": closed_equals_visualized,
        "visualization_mismatch_ignored_due_to_no_charts": visualization_mismatch_ignored_due_to_no_charts,
        "status": status,
    }


def write_lifecycle_report(
    result: Dict[str, Any],
    charts_dir: str,
    output_path: str,
    *,
    charting_enabled: bool = True,
) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report = build_lifecycle_report(
        trades=result.get("trades", []),
        risk_events=int(result.get("risk_events", 0) or 0),
        risk_bearing_snapshots=int(result.get("risk_bearing_snapshots", 0) or 0),
        visualized_trades=count_visualized_trades(charts_dir),
        charting_enabled=charting_enabled,
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report
