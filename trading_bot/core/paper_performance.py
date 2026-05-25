"""Prompt 29.2 paper performance, drift and dashboard utilities.

This module is intentionally read-only with respect to trading logic.  It reads
paper runtime artifacts and writes operator-facing reports:

- data/paper_performance_report.json
- data/paper_drift_report.json
- data/paper_dashboard.html

The reports are designed to work even when there are zero trades, because early
paper validation often produces only scan/no-signal cycles.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any
import json
import math
import re

from core.paper_lifecycle import build_lifecycle_report, read_events


CYCLE_ID_RE = re.compile(r"pc_(\d+)_[0-9a-fA-F]+")


@dataclass(frozen=True)
class PaperPerformancePaths:
    data_dir: Path

    @property
    def state_path(self) -> Path:
        return self.data_dir / "paper_state.json"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "paper_status.json"

    @property
    def events_path(self) -> Path:
        return self.data_dir / "paper_events.jsonl"

    @property
    def lifecycle_path(self) -> Path:
        return self.data_dir / "paper_lifecycle_report.json"

    @property
    def performance_path(self) -> Path:
        return self.data_dir / "paper_performance_report.json"

    @property
    def drift_path(self) -> Path:
        return self.data_dir / "paper_drift_report.json"

    @property
    def dashboard_path(self) -> Path:
        return self.data_dir / "paper_dashboard.html"

    @property
    def position_monitor_path(self) -> Path:
        return self.data_dir / "paper_position_monitor.json"

    @property
    def signal_diagnostics_path(self) -> Path:
        return self.data_dir / "paper_signal_diagnostics_report.json"

    @property
    def signal_diagnostics_backfill_path(self) -> Path:
        return self.data_dir / "paper_signal_diagnostics_backfill_report.json"

    @property
    def shadow_unlock_path(self) -> Path:
        return self.data_dir / "paper_shadow_unlock_report.json"

    @property
    def unlock_rejection_path(self) -> Path:
        return self.data_dir / "paper_unlock_rejection_report.json"

    @property
    def crypto_scenario_path(self) -> Path:
        return self.data_dir / "crypto_intraday_scenario_report.json"

    @property
    def candlestick_pattern_path(self) -> Path:
        return self.data_dir / "candlestick_pattern_report.json"

    @property
    def pattern_conditioned_shadow_path(self) -> Path:
        return self.data_dir / "pattern_conditioned_shadow_report.json"

    @property
    def scenario_pattern_calibration_path(self) -> Path:
        return self.data_dir / "scenario_pattern_calibration_report.json"

    @property
    def market_structure_map_path(self) -> Path:
        return self.data_dir / "market_structure_map_report.json"

    @property
    def calibrated_structure_shadow_path(self) -> Path:
        return self.data_dir / "calibrated_structure_shadow_report.json"

    @property
    def structure_filter_diagnostics_path(self) -> Path:
        return self.data_dir / "structure_filter_diagnostics_report.json"

    @property
    def structure_context_repair_path(self) -> Path:
        return self.data_dir / "structure_context_repair_report.json"

    @property
    def repaired_structure_shadow_validation_path(self) -> Path:
        return self.data_dir / "repaired_structure_shadow_validation_report.json"

    @property
    def independent_repaired_validation_path(self) -> Path:
        return self.data_dir / "independent_repaired_validation_report.json"

    @property
    def paper_unlock_profile_refinement_path(self) -> Path:
        return self.data_dir / "paper_unlock_profile_refinement_report.json"

    @property
    def cost_stress_path(self) -> Path:
        return self.data_dir / "execution_cost_stress_report.json"

    @property
    def robustness_path(self) -> Path:
        return self.data_dir / "multi_asset_robustness_report.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"__read_error__": str(exc)}


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "").upper()


def _ts_to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return default


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100.0


def _cycle_seq(cycle_id: str) -> int | None:
    match = CYCLE_ID_RE.fullmatch(str(cycle_id or ""))
    return int(match.group(1)) if match else None


def _position_from_event(event: dict[str, Any]) -> dict[str, Any]:
    position = event.get("position")
    return position if isinstance(position, dict) else {}


def _order_from_event(event: dict[str, Any]) -> dict[str, Any]:
    order = event.get("order")
    return order if isinstance(order, dict) else {}


def _equity_curve(events: list[dict[str, Any]], fallback_status: dict[str, Any]) -> list[dict[str, Any]]:
    curve: list[dict[str, Any]] = []
    for event in events:
        if _event_type(event) != "CYCLE_COMPLETED":
            continue
        equity = _safe_float(event.get("equity"), float("nan"))
        balance = _safe_float(event.get("balance"), float("nan"))
        if not math.isfinite(equity):
            equity = _safe_float(fallback_status.get("equity"), _safe_float(fallback_status.get("balance"), 0.0))
        if not math.isfinite(balance):
            balance = _safe_float(fallback_status.get("balance"), equity)
        curve.append(
            {
                "ts": event.get("ts"),
                "cycle_id": event.get("cycle_id"),
                "cycle_seq": _cycle_seq(str(event.get("cycle_id") or "")),
                "equity": round(equity, 8),
                "balance": round(balance, 8),
                "scanned": int(event.get("scanned") or 0),
                "signals": int(event.get("signals") or 0),
                "orders": int(event.get("orders") or 0),
                "errors": int(event.get("errors") or 0),
                "no_signal": int(event.get("no_signal") or 0),
                "open_positions": int(event.get("open_positions") or 0),
            }
        )
    return curve


def _max_drawdown_pct(curve: list[dict[str, Any]], current_dd: float = 0.0) -> float:
    peak = None
    max_dd = max(0.0, current_dd)
    for point in curve:
        equity = _safe_float(point.get("equity"), 0.0)
        if equity <= 0:
            continue
        peak = equity if peak is None else max(peak, equity)
        if peak and peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return round(max_dd, 6)


def _cycle_durations(events: list[dict[str, Any]]) -> list[float]:
    starts: dict[str, datetime] = {}
    durations: list[float] = []
    for event in events:
        etype = _event_type(event)
        cycle_id = str(event.get("cycle_id") or "")
        dt = _ts_to_dt(event.get("ts"))
        if not cycle_id or dt is None:
            continue
        if etype == "CYCLE_STARTED":
            starts[cycle_id] = dt
        elif etype == "CYCLE_COMPLETED" and cycle_id in starts:
            durations.append(max(0.0, (dt - starts[cycle_id]).total_seconds()))
    return durations


def _group_symbol_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    raw: dict[str, Counter[str]] = defaultdict(Counter)
    pnl_by_symbol: dict[str, list[float]] = defaultdict(list)
    for event in events:
        symbol = str(event.get("symbol") or "")
        etype = _event_type(event)
        if not symbol:
            position = _position_from_event(event)
            symbol = str(position.get("symbol") or "")
        if not symbol:
            continue
        if etype in {
            "ASSET_SCANNED",
            "NO_SIGNAL",
            "SIGNAL_DETECTED",
            "PAPER_UNLOCK_SIGNAL",
            "SIGNAL_REJECTED",
            "PAPER_ORDER_SUBMITTED",
            "ORDER_FILLED",
            "POSITION_OPENED",
            "POSITION_CLOSED",
            "SYMBOL_ERROR",
            "ASSET_SKIPPED",
        }:
            raw[symbol][etype] += 1
        if etype == "POSITION_CLOSED":
            position = _position_from_event(event)
            pnl_by_symbol[symbol].append(_safe_float(position.get("realized_pnl"), 0.0))

    out: dict[str, dict[str, Any]] = {}
    for symbol, counts in sorted(raw.items()):
        closed_pnls = pnl_by_symbol.get(symbol, [])
        wins = sum(1 for x in closed_pnls if x > 0)
        losses = sum(1 for x in closed_pnls if x < 0)
        out[symbol] = {
            "scanned": counts.get("ASSET_SCANNED", 0),
            "signals": counts.get("SIGNAL_DETECTED", 0),
            "paper_unlock_signals": counts.get("PAPER_UNLOCK_SIGNAL", 0),
            "orders_submitted": counts.get("PAPER_ORDER_SUBMITTED", 0),
            "orders_filled": counts.get("ORDER_FILLED", 0),
            "positions_opened": counts.get("POSITION_OPENED", 0),
            "positions_closed": counts.get("POSITION_CLOSED", 0),
            "no_signal": counts.get("NO_SIGNAL", 0),
            "signal_rejected": counts.get("SIGNAL_REJECTED", 0),
            "skipped": counts.get("ASSET_SKIPPED", 0),
            "errors": counts.get("SYMBOL_ERROR", 0),
            "no_signal_ratio_pct": round(_pct(counts.get("NO_SIGNAL", 0), max(1, counts.get("ASSET_SCANNED", 0))), 4),
            "closed_trade_pnl_total": round(sum(closed_pnls), 8),
            "closed_trade_expectancy": round(mean(closed_pnls), 8) if closed_pnls else 0.0,
            "win_rate_pct": round(_pct(wins, wins + losses), 4) if wins + losses else 0.0,
        }
    return out


def _group_archetype_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pnls: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        etype = _event_type(event)
        if etype not in {"POSITION_OPENED", "POSITION_CLOSED", "PAPER_ORDER_SUBMITTED", "ORDER_FILLED"}:
            continue
        position = _position_from_event(event)
        order = _order_from_event(event)
        metadata = position.get("metadata") if isinstance(position.get("metadata"), dict) else {}
        if not metadata and isinstance(order.get("metadata"), dict):
            metadata = order.get("metadata", {})
        archetype = str(
            metadata.get("setup_archetype")
            or metadata.get("archetype")
            or metadata.get("combination")
            or "UNCLASSIFIED"
        )
        counts[archetype][etype] += 1
        if etype == "POSITION_CLOSED":
            pnls[archetype].append(_safe_float(position.get("realized_pnl"), 0.0))
    out: dict[str, dict[str, Any]] = {}
    for archetype in sorted(set(counts) | set(pnls)):
        closed_pnls = pnls.get(archetype, [])
        wins = sum(1 for x in closed_pnls if x > 0)
        losses = sum(1 for x in closed_pnls if x < 0)
        out[archetype] = {
            "orders_submitted": counts[archetype].get("PAPER_ORDER_SUBMITTED", 0),
            "orders_filled": counts[archetype].get("ORDER_FILLED", 0),
            "positions_opened": counts[archetype].get("POSITION_OPENED", 0),
            "positions_closed": counts[archetype].get("POSITION_CLOSED", 0),
            "closed_trade_pnl_total": round(sum(closed_pnls), 8),
            "closed_trade_expectancy": round(mean(closed_pnls), 8) if closed_pnls else 0.0,
            "win_rate_pct": round(_pct(wins, wins + losses), 4) if wins + losses else 0.0,
        }
    return out


def _expected_backtest(paths: PaperPerformancePaths, cost_model: str) -> dict[str, Any]:
    stress = _read_json(paths.cost_stress_path)
    summary = stress.get("summary", {}) if isinstance(stress.get("summary"), dict) else {}
    by_cost = summary.get("by_cost_model", {}) if isinstance(summary.get("by_cost_model"), dict) else {}
    expected = by_cost.get(cost_model, {}) if isinstance(by_cost.get(cost_model), dict) else {}
    if expected:
        return {
            "source": str(paths.cost_stress_path),
            "cost_model": cost_model,
            "average_net_pnl_pct": _safe_float(expected.get("average_net_pnl_pct"), 0.0),
            "worst_max_drawdown_pct": _safe_float(expected.get("worst_max_drawdown_pct"), 0.0),
            "total_closed_trades": int(expected.get("total_closed_trades") or 0),
            "positive_asset_count": int(expected.get("positive_asset_count") or 0),
            "tested_assets": expected.get("tested_assets", []),
            "robust_positive_archetypes": expected.get("robust_positive_archetypes", []),
        }
    robustness = _read_json(paths.robustness_path)
    rsummary = robustness.get("summary", {}) if isinstance(robustness.get("summary"), dict) else {}
    return {
        "source": str(paths.robustness_path),
        "cost_model": cost_model,
        "average_net_pnl_pct": 0.0,
        "worst_max_drawdown_pct": 0.0,
        "total_closed_trades": int(rsummary.get("total_closed_trades") or 0),
        "positive_asset_count": int(rsummary.get("positive_asset_count") or 0),
        "tested_assets": rsummary.get("tested_assets", []),
        "robust_positive_archetypes": rsummary.get("robust_positive_archetypes", []),
    }


def build_performance_report(data_dir: str | Path) -> dict[str, Any]:
    paths = PaperPerformancePaths(Path(data_dir))
    state = _read_json(paths.state_path)
    status = _read_json(paths.status_path)
    lifecycle = _read_json(paths.lifecycle_path) or build_lifecycle_report(paths.data_dir)
    position_monitor = _read_json(paths.position_monitor_path)
    signal_diagnostics = _read_json(paths.signal_diagnostics_path)
    signal_diagnostics_backfill = _read_json(paths.signal_diagnostics_backfill_path)
    shadow_unlock = _read_json(paths.shadow_unlock_path)
    unlock_rejection = _read_json(paths.unlock_rejection_path)
    crypto_scenario = _read_json(paths.crypto_scenario_path)
    candlestick_patterns = _read_json(paths.candlestick_pattern_path)
    pattern_conditioned_shadow = _read_json(paths.pattern_conditioned_shadow_path)
    scenario_pattern_calibration = _read_json(paths.scenario_pattern_calibration_path)
    market_structure_map = _read_json(paths.market_structure_map_path)
    calibrated_structure_shadow = _read_json(paths.calibrated_structure_shadow_path)
    structure_filter_diagnostics = _read_json(paths.structure_filter_diagnostics_path)
    structure_context_repair = _read_json(paths.structure_context_repair_path)
    repaired_structure_shadow_validation = _read_json(paths.repaired_structure_shadow_validation_path)
    independent_repaired_validation = _read_json(paths.independent_repaired_validation_path)
    paper_unlock_profile_refinement = _read_json(paths.paper_unlock_profile_refinement_path)
    events = read_events(paths.events_path)
    event_counts = Counter(_event_type(e) for e in events)
    curve = _equity_curve(events, status)
    durations = _cycle_durations(events)

    initial_balance = _safe_float(state.get("initial_balance"), _safe_float(status.get("balance"), 1000.0))
    balance = _safe_float(status.get("balance"), _safe_float(state.get("balance"), initial_balance))
    equity = _safe_float(status.get("equity"), balance)
    realized = _safe_float(status.get("realized_pnl"), _safe_float(state.get("realized_pnl"), 0.0))
    unrealized = _safe_float(status.get("unrealized_pnl"), 0.0)
    current_dd = _safe_float(status.get("drawdown_pct"), _safe_float(state.get("drawdown_pct"), 0.0))
    closed_positions = [p for p in (state.get("positions", {}) or {}).values() if isinstance(p, dict) and str(p.get("status", "")).upper() == "CLOSED"]
    wins = sum(1 for p in closed_positions if _safe_float(p.get("realized_pnl"), 0.0) > 0)
    losses = sum(1 for p in closed_positions if _safe_float(p.get("realized_pnl"), 0.0) < 0)
    closed_pnls = [_safe_float(p.get("realized_pnl"), 0.0) for p in closed_positions]

    scanned = event_counts.get("ASSET_SCANNED", 0)
    no_signal = event_counts.get("NO_SIGNAL", 0)
    symbol_errors = event_counts.get("SYMBOL_ERROR", 0)
    orders_submitted = event_counts.get("PAPER_ORDER_SUBMITTED", 0)
    rejected = event_counts.get("SIGNAL_REJECTED", 0) + event_counts.get("ORDER_REJECTED", 0)
    skipped = event_counts.get("ASSET_SKIPPED", 0) + event_counts.get("TICK_SKIPPED", 0)

    warnings: list[str] = []
    if lifecycle.get("status") == "FAIL":
        warnings.append("lifecycle_report_FAIL")
    if scanned >= 20 and _pct(no_signal, scanned) >= 98.0:
        warnings.append("NO_SIGNAL_RATE_WARN")
    if scanned >= 10 and _pct(symbol_errors, scanned) >= 10.0:
        warnings.append("EXCHANGE_ERROR_RATE_WARN")
    if len(closed_positions) == 0:
        warnings.append("NO_CLOSED_TRADES_YET")

    report = {
        "generated_at": utc_now_iso(),
        "status": "WARN" if warnings else "PASS",
        "warnings": warnings,
        "runtime_files": {
            "state": str(paths.state_path),
            "events": str(paths.events_path),
            "status": str(paths.status_path),
            "lifecycle": str(paths.lifecycle_path),
            "position_monitor": str(paths.position_monitor_path),
            "signal_diagnostics": str(paths.signal_diagnostics_path),
            "signal_diagnostics_backfill": str(paths.signal_diagnostics_backfill_path),
            "shadow_unlock": str(paths.shadow_unlock_path),
            "unlock_rejection": str(paths.unlock_rejection_path),
            "crypto_scenario": str(paths.crypto_scenario_path),
            "candlestick_patterns": str(paths.candlestick_pattern_path),
            "pattern_conditioned_shadow": str(paths.pattern_conditioned_shadow_path),
            "scenario_pattern_calibration": str(paths.scenario_pattern_calibration_path),
            "market_structure_map": str(paths.market_structure_map_path),
            "calibrated_structure_shadow": str(paths.calibrated_structure_shadow_path),
            "structure_filter_diagnostics": str(paths.structure_filter_diagnostics_path),
            "structure_context_repair": str(paths.structure_context_repair_path),
            "repaired_structure_shadow_validation": str(paths.repaired_structure_shadow_validation_path),
            "independent_repaired_validation": str(paths.independent_repaired_validation_path),
            "paper_unlock_profile_refinement": str(paths.paper_unlock_profile_refinement_path),
        },
        "engine": {
            "mode": status.get("mode", "paper"),
            "symbols": status.get("symbols", []),
            "timeframe": status.get("timeframe"),
            "cost_model": status.get("cost_model"),
            "cycle_seq": status.get("cycle_seq"),
            "last_cycle_time": curve[-1].get("ts") if curve else status.get("updated_at"),
            "telegram_status": "runtime_optional",
            "telegram_enabled": bool(status.get("telegram_enabled", False)),
            "telegram_proactive": status.get("telegram_proactive", {}),
            "operational_console": status.get("operational_console", {}),
            "signal_diagnostics_enabled": bool(status.get("signal_diagnostics_enabled", False)),
            "signal_diagnostics_backfill_enabled": bool(status.get("signal_diagnostics_backfill_enabled", False)),
            "paper_entry_unlock_enabled": bool(status.get("paper_entry_unlock_enabled", False)),
            "paper_unlock": status.get("paper_unlock", {}),
            "exploratory_signal_analysis": bool(status.get("exploratory_signal_analysis", False)),
            "shadow_simulation_enabled": bool(status.get("shadow_simulation_enabled", False)),
            "crypto_scenario_enabled": bool(status.get("crypto_scenario_enabled", True)),
            "candlestick_patterns_enabled": bool(status.get("candlestick_patterns_enabled", True)),
            "pattern_conditioned_shadow_enabled": bool(status.get("pattern_conditioned_shadow_enabled", True)),
            "scenario_pattern_calibration_enabled": bool(status.get("scenario_pattern_calibration_enabled", True)),
            "market_structure_map_enabled": bool(status.get("market_structure_map_enabled", True)),
            "kill_switch": bool(status.get("kill_switch", state.get("kill_switch", False))),
            "is_paused": bool(status.get("is_paused", state.get("is_paused", False))),
        },
        "equity": {
            "initial_balance": round(initial_balance, 8),
            "balance": round(balance, 8),
            "equity": round(equity, 8),
            "realized_pnl": round(realized, 8),
            "unrealized_pnl": round(unrealized, 8),
            "return_pct": round(_pct(equity - initial_balance, initial_balance), 6),
            "drawdown_pct": round(current_dd, 6),
            "max_observed_drawdown_pct": _max_drawdown_pct(curve, current_dd),
            "equity_curve": curve[-500:],
        },
        "cycles": {
            "started": int((lifecycle.get("cycles") or {}).get("started") or 0),
            "completed": int((lifecycle.get("cycles") or {}).get("completed") or 0),
            "interrupted": int((lifecycle.get("cycles") or {}).get("interrupted") or 0),
            "avg_cycle_seconds": round(mean(durations), 4) if durations else 0.0,
            "last_cycle": curve[-1] if curve else {},
        },
        "signals": {
            "asset_scans": scanned,
            "signals_detected": event_counts.get("SIGNAL_DETECTED", 0),
            "paper_unlock_signals": event_counts.get("PAPER_UNLOCK_SIGNAL", 0),
            "paper_unlock_evaluated": event_counts.get("PAPER_UNLOCK_EVALUATED", 0),
            "signals_rejected": event_counts.get("SIGNAL_REJECTED", 0),
            "no_signal": no_signal,
            "no_signal_ratio_pct": round(_pct(no_signal, scanned), 4),
            "skipped": skipped,
            "diagnostics": (signal_diagnostics.get("counts") or {}).get("diagnostics", 0) if isinstance(signal_diagnostics, dict) else 0,
            "backfill_diagnostics": (signal_diagnostics_backfill.get("counts") or {}).get("inferred_diagnostics", 0) if isinstance(signal_diagnostics_backfill, dict) else 0,
            "combined_diagnostics": (signal_diagnostics_backfill.get("counts") or {}).get("combined_diagnostics", 0) if isinstance(signal_diagnostics_backfill, dict) else 0,
            "near_candidates": ((signal_diagnostics_backfill.get("counts") or {}).get("near_candidates", 0) if isinstance(signal_diagnostics_backfill, dict) and signal_diagnostics_backfill else (signal_diagnostics.get("counts") or {}).get("near_candidates", 0) if isinstance(signal_diagnostics, dict) else 0),
            "exploratory_candidates": ((signal_diagnostics_backfill.get("counts") or {}).get("exploratory_candidates", 0) if isinstance(signal_diagnostics_backfill, dict) and signal_diagnostics_backfill else (signal_diagnostics.get("counts") or {}).get("exploratory_candidates", 0) if isinstance(signal_diagnostics, dict) else 0),
            "dominant_filters": ((signal_diagnostics_backfill.get("dominant_filters") or {}).get("combined", {}) if isinstance(signal_diagnostics_backfill, dict) and signal_diagnostics_backfill else signal_diagnostics.get("dominant_filters", {}) if isinstance(signal_diagnostics, dict) else {}),
            "shadow_rows_total": (shadow_unlock.get("counts") or {}).get("shadow_rows_total", 0) if isinstance(shadow_unlock, dict) else 0,
            "unlock_rejection_status": unlock_rejection.get("status", "NA") if isinstance(unlock_rejection, dict) else "NA",
            "unlock_rejection_decision": ((unlock_rejection.get("decision") or {}).get("status") if isinstance(unlock_rejection.get("decision"), dict) else "NA") if isinstance(unlock_rejection, dict) else "NA",
            "unlock_rejection_dominant_btc_reason": ((unlock_rejection.get("decision") or {}).get("dominant_btc_reason") if isinstance(unlock_rejection.get("decision"), dict) else "") if isinstance(unlock_rejection, dict) else "",
            "unlock_rejection_btc_evaluated": (unlock_rejection.get("counts") or {}).get("btc_evaluated", 0) if isinstance(unlock_rejection, dict) else 0,
            "unlock_rejection_btc_near_candidates": (unlock_rejection.get("counts") or {}).get("btc_near_threshold_candidates", 0) if isinstance(unlock_rejection, dict) else 0,
            "crypto_scenario_status": crypto_scenario.get("status", "NA") if isinstance(crypto_scenario, dict) else "NA",
            "crypto_scenario_decision": ((crypto_scenario.get("decision") or {}).get("status") if isinstance(crypto_scenario.get("decision"), dict) else "NA") if isinstance(crypto_scenario, dict) else "NA",
            "crypto_scenario_btc_rows": (crypto_scenario.get("counts") or {}).get("btc_scenario_events", 0) if isinstance(crypto_scenario, dict) else 0,
            "candlestick_pattern_status": candlestick_patterns.get("status", "NA") if isinstance(candlestick_patterns, dict) else "NA",
            "candlestick_pattern_decision": ((candlestick_patterns.get("decision") or {}).get("status") if isinstance(candlestick_patterns.get("decision"), dict) else "NA") if isinstance(candlestick_patterns, dict) else "NA",
            "candlestick_pattern_btc_rows": (candlestick_patterns.get("counts") or {}).get("btc_pattern_events", 0) if isinstance(candlestick_patterns, dict) else 0,
            "pattern_conditioned_shadow_status": pattern_conditioned_shadow.get("status", "NA") if isinstance(pattern_conditioned_shadow, dict) else "NA",
            "pattern_conditioned_shadow_decision": ((pattern_conditioned_shadow.get("decision") or {}).get("status") if isinstance(pattern_conditioned_shadow.get("decision"), dict) else "NA") if isinstance(pattern_conditioned_shadow, dict) else "NA",
            "pattern_conditioned_historical_candidates": (pattern_conditioned_shadow.get("counts") or {}).get("historical_candidates", 0) if isinstance(pattern_conditioned_shadow, dict) else 0,
            "scenario_pattern_calibration_status": scenario_pattern_calibration.get("status", "NA") if isinstance(scenario_pattern_calibration, dict) else "NA",
            "scenario_pattern_calibration_decision": ((scenario_pattern_calibration.get("decision") or {}).get("status") if isinstance(scenario_pattern_calibration.get("decision"), dict) else "NA") if isinstance(scenario_pattern_calibration, dict) else "NA",
            "scenario_pattern_historical_candidates": (scenario_pattern_calibration.get("counts") or {}).get("historical_candidates", 0) if isinstance(scenario_pattern_calibration, dict) else 0,
            "scenario_pattern_focus_profile": (((scenario_pattern_calibration.get("decision") or {}).get("candidate_profile") or {}).get("name") if isinstance(((scenario_pattern_calibration.get("decision") or {}).get("candidate_profile") if isinstance(scenario_pattern_calibration.get("decision"), dict) else {}), dict) else "") if isinstance(scenario_pattern_calibration, dict) else "",
            "market_structure_map_status": market_structure_map.get("status", "NA") if isinstance(market_structure_map, dict) else "NA",
            "market_structure_map_decision": ((market_structure_map.get("decision") or {}).get("status") if isinstance(market_structure_map.get("decision"), dict) else "NA") if isinstance(market_structure_map, dict) else "NA",
            "market_structure_snapshots": (market_structure_map.get("counts") or {}).get("historical_snapshots_evaluated", 0) if isinstance(market_structure_map, dict) else 0,
            "market_structure_focus_bias": (((market_structure_map.get("decision") or {}).get("focus_latest") or {}).get("structure_bias") if isinstance(((market_structure_map.get("decision") or {}).get("focus_latest") if isinstance(market_structure_map.get("decision"), dict) else {}), dict) else "") if isinstance(market_structure_map, dict) else "",
            "market_structure_focus_confirmation": (((market_structure_map.get("decision") or {}).get("focus_latest") or {}).get("confirmation_summary") if isinstance(((market_structure_map.get("decision") or {}).get("focus_latest") if isinstance(market_structure_map.get("decision"), dict) else {}), dict) else "") if isinstance(market_structure_map, dict) else "",
            "calibrated_structure_shadow_status": calibrated_structure_shadow.get("status", "NA") if isinstance(calibrated_structure_shadow, dict) else "NA",
            "calibrated_structure_shadow_decision": ((calibrated_structure_shadow.get("decision") or {}).get("status") if isinstance(calibrated_structure_shadow.get("decision"), dict) else "NA") if isinstance(calibrated_structure_shadow, dict) else "NA",
            "calibrated_structure_rows": (calibrated_structure_shadow.get("counts") or {}).get("structured_candidate_rows", 0) if isinstance(calibrated_structure_shadow, dict) else 0,
            "calibrated_structure_best_variant": (((calibrated_structure_shadow.get("decision") or {}).get("best_variant") or (calibrated_structure_shadow.get("decision") or {}).get("best_watchlist_variant") or {}).get("name") if isinstance(((calibrated_structure_shadow.get("decision") or {}).get("best_variant") or (calibrated_structure_shadow.get("decision") or {}).get("best_watchlist_variant") if isinstance(calibrated_structure_shadow.get("decision"), dict) else {}), dict) else "") if isinstance(calibrated_structure_shadow, dict) else "",
            "structure_filter_diagnostics_status": structure_filter_diagnostics.get("status", "NA") if isinstance(structure_filter_diagnostics, dict) else "NA",
            "structure_filter_diagnostics_decision": ((structure_filter_diagnostics.get("decision") or {}).get("status") if isinstance(structure_filter_diagnostics.get("decision"), dict) else "NA") if isinstance(structure_filter_diagnostics, dict) else "NA",
            "structure_filter_rows": (structure_filter_diagnostics.get("counts") or {}).get("structured_candidate_rows", 0) if isinstance(structure_filter_diagnostics, dict) else 0,
            "structure_filter_best_variant": (((structure_filter_diagnostics.get("decision") or {}).get("best_audit_variant") or {}).get("name") if isinstance(((structure_filter_diagnostics.get("decision") or {}).get("best_audit_variant") if isinstance(structure_filter_diagnostics.get("decision"), dict) else {}), dict) else "") if isinstance(structure_filter_diagnostics, dict) else "",
            "structure_context_repair_status": structure_context_repair.get("status", "NA") if isinstance(structure_context_repair, dict) else "NA",
            "structure_context_repair_decision": ((structure_context_repair.get("decision") or {}).get("status") if isinstance(structure_context_repair.get("decision"), dict) else "NA") if isinstance(structure_context_repair, dict) else "NA",
            "structure_context_repair_rows": (structure_context_repair.get("counts") or {}).get("structured_candidate_rows", 0) if isinstance(structure_context_repair, dict) else 0,
            "structure_context_repair_best_variant": (((structure_context_repair.get("decision") or {}).get("best_repaired_variant") or {}).get("name") if isinstance(((structure_context_repair.get("decision") or {}).get("best_repaired_variant") if isinstance(structure_context_repair.get("decision"), dict) else {}), dict) else "") if isinstance(structure_context_repair, dict) else "",
            "repaired_structure_shadow_validation_status": repaired_structure_shadow_validation.get("status", "NA") if isinstance(repaired_structure_shadow_validation, dict) else "NA",
            "repaired_structure_shadow_validation_decision": ((repaired_structure_shadow_validation.get("decision") or {}).get("status") if isinstance(repaired_structure_shadow_validation.get("decision"), dict) else "NA") if isinstance(repaired_structure_shadow_validation, dict) else "NA",
            "repaired_structure_shadow_validation_rows": (repaired_structure_shadow_validation.get("counts") or {}).get("structured_candidate_rows", 0) if isinstance(repaired_structure_shadow_validation, dict) else 0,
            "repaired_structure_shadow_validation_best_variant": (((repaired_structure_shadow_validation.get("decision") or {}).get("best_validation_variant") or {}).get("name") if isinstance(((repaired_structure_shadow_validation.get("decision") or {}).get("best_validation_variant") if isinstance(repaired_structure_shadow_validation.get("decision"), dict) else {}), dict) else "") if isinstance(repaired_structure_shadow_validation, dict) else "",
            "independent_repaired_validation_status": independent_repaired_validation.get("status", "NA") if isinstance(independent_repaired_validation, dict) else "NA",
            "independent_repaired_validation_decision": ((independent_repaired_validation.get("decision") or {}).get("status") if isinstance(independent_repaired_validation.get("decision"), dict) else "NA") if isinstance(independent_repaired_validation, dict) else "NA",
            "independent_repaired_validation_rows": (independent_repaired_validation.get("counts") or {}).get("target_candidate_rows", 0) if isinstance(independent_repaired_validation, dict) else 0,
            "independent_repaired_validation_best_variant": (((independent_repaired_validation.get("decision") or {}).get("best_stability_variant") or {}).get("name") if isinstance(((independent_repaired_validation.get("decision") or {}).get("best_stability_variant") if isinstance(independent_repaired_validation.get("decision"), dict) else {}), dict) else "") if isinstance(independent_repaired_validation, dict) else "",
            "paper_unlock_profile_refinement_status": paper_unlock_profile_refinement.get("status", "NA") if isinstance(paper_unlock_profile_refinement, dict) else "NA",
            "paper_unlock_profile_refinement_decision": ((paper_unlock_profile_refinement.get("decision") or {}).get("status") if isinstance(paper_unlock_profile_refinement.get("decision"), dict) else "NA") if isinstance(paper_unlock_profile_refinement, dict) else "NA",
            "paper_unlock_profile_refinement_rows": (paper_unlock_profile_refinement.get("counts") or {}).get("target_candidate_rows", 0) if isinstance(paper_unlock_profile_refinement, dict) else 0,
            "paper_unlock_profile_refinement_profile": ((paper_unlock_profile_refinement.get("decision") or {}).get("profile_name") if isinstance(paper_unlock_profile_refinement.get("decision"), dict) else "") if isinstance(paper_unlock_profile_refinement, dict) else "",
        },
        "orders": {
            "submitted": orders_submitted,
            "filled": event_counts.get("ORDER_FILLED", 0) + event_counts.get("PAPER_ORDER_FILLED", 0),
            "rejected": rejected,
            "pending": int(status.get("pending_orders") or 0),
        },
        "position_monitor": position_monitor if isinstance(position_monitor, dict) else {},
        "signal_diagnostics": signal_diagnostics if isinstance(signal_diagnostics, dict) else {},
        "signal_diagnostics_backfill": signal_diagnostics_backfill if isinstance(signal_diagnostics_backfill, dict) else {},
        "shadow_unlock": shadow_unlock if isinstance(shadow_unlock, dict) else {},
        "unlock_rejection_analysis": unlock_rejection if isinstance(unlock_rejection, dict) else {},
        "crypto_scenario": crypto_scenario if isinstance(crypto_scenario, dict) else {},
        "candlestick_patterns": candlestick_patterns if isinstance(candlestick_patterns, dict) else {},
        "pattern_conditioned_shadow": pattern_conditioned_shadow if isinstance(pattern_conditioned_shadow, dict) else {},
        "scenario_pattern_calibration": scenario_pattern_calibration if isinstance(scenario_pattern_calibration, dict) else {},
        "market_structure_map": market_structure_map if isinstance(market_structure_map, dict) else {},
        "calibrated_structure_shadow": calibrated_structure_shadow if isinstance(calibrated_structure_shadow, dict) else {},
        "structure_filter_diagnostics": structure_filter_diagnostics if isinstance(structure_filter_diagnostics, dict) else {},
        "structure_context_repair": structure_context_repair if isinstance(structure_context_repair, dict) else {},
        "repaired_structure_shadow_validation": repaired_structure_shadow_validation if isinstance(repaired_structure_shadow_validation, dict) else {},
        "independent_repaired_validation": independent_repaired_validation if isinstance(independent_repaired_validation, dict) else {},
        "paper_unlock_profile_refinement": paper_unlock_profile_refinement if isinstance(paper_unlock_profile_refinement, dict) else {},
        "positions": {
            "open": int(status.get("open_positions") or 0),
            "closed": len(closed_positions),
            "win_rate_pct": round(_pct(wins, wins + losses), 4) if wins + losses else 0.0,
            "expectancy": round(mean(closed_pnls), 8) if closed_pnls else 0.0,
            "gross_closed_pnl": round(sum(closed_pnls), 8),
        },
        "errors": {
            "symbol_errors": symbol_errors,
            "exchange_error_rate_pct": round(_pct(symbol_errors, scanned), 4),
            "market_data_empty": event_counts.get("MARKET_DATA_EMPTY", 0),
        },
        "by_asset": _group_symbol_stats(events),
        "by_archetype": _group_archetype_stats(events),
        "recent_events": [
            {k: v for k, v in event.items() if not k.startswith("__")}
            for event in events[-25:]
        ],
    }
    return report


def build_drift_report(data_dir: str | Path, performance: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = PaperPerformancePaths(Path(data_dir))
    performance = performance or build_performance_report(paths.data_dir)
    cost_model = str((performance.get("engine") or {}).get("cost_model") or "conservative")
    expected = _expected_backtest(paths, cost_model)
    alerts: list[dict[str, Any]] = []

    equity = performance.get("equity", {}) if isinstance(performance.get("equity"), dict) else {}
    signals = performance.get("signals", {}) if isinstance(performance.get("signals"), dict) else {}
    positions = performance.get("positions", {}) if isinstance(performance.get("positions"), dict) else {}
    errors = performance.get("errors", {}) if isinstance(performance.get("errors"), dict) else {}
    by_asset = performance.get("by_asset", {}) if isinstance(performance.get("by_asset"), dict) else {}
    by_archetype = performance.get("by_archetype", {}) if isinstance(performance.get("by_archetype"), dict) else {}

    max_dd = _safe_float(equity.get("max_observed_drawdown_pct"), 0.0)
    expected_dd = _safe_float(expected.get("worst_max_drawdown_pct"), 0.0)
    dd_warn_threshold = max(10.0, expected_dd * 1.5) if expected_dd > 0 else 10.0
    if max_dd > dd_warn_threshold:
        alerts.append({"code": "PAPER_DD_WARN", "severity": "WARN", "observed_pct": max_dd, "threshold_pct": round(dd_warn_threshold, 4)})

    closed = int(positions.get("closed") or 0)
    expectancy = _safe_float(positions.get("expectancy"), 0.0)
    if closed >= 10 and expectancy <= 0:
        alerts.append({"code": "PAPER_EXPECTANCY_WARN", "severity": "WARN", "closed_trades": closed, "expectancy": expectancy})
    elif closed < 10:
        alerts.append({"code": "PAPER_SAMPLE_LOW", "severity": "INFO", "closed_trades": closed, "message": "Drift checks are provisional until at least 10 closed paper trades."})

    no_signal_ratio = _safe_float(signals.get("no_signal_ratio_pct"), 0.0)
    scans = int(signals.get("asset_scans") or 0)
    if scans >= 20 and no_signal_ratio >= 98.0:
        alerts.append({"code": "NO_SIGNAL_RATE_WARN", "severity": "WARN", "asset_scans": scans, "no_signal_ratio_pct": no_signal_ratio})

    error_rate = _safe_float(errors.get("exchange_error_rate_pct"), 0.0)
    if scans >= 10 and error_rate >= 10.0:
        alerts.append({"code": "EXCHANGE_ERROR_RATE_WARN", "severity": "WARN", "exchange_error_rate_pct": error_rate})

    for symbol, row in by_asset.items():
        if not isinstance(row, dict):
            continue
        if int(row.get("positions_closed") or 0) >= 5 and _safe_float(row.get("closed_trade_expectancy"), 0.0) <= 0:
            alerts.append({"code": "ASSET_DRIFT_WARN", "severity": "WARN", "symbol": symbol, "expectancy": row.get("closed_trade_expectancy")})

    for archetype, row in by_archetype.items():
        if not isinstance(row, dict):
            continue
        if int(row.get("positions_closed") or 0) >= 5 and _safe_float(row.get("closed_trade_expectancy"), 0.0) <= 0:
            alerts.append({"code": "ARCHETYPE_DRIFT_WARN", "severity": "WARN", "archetype": archetype, "expectancy": row.get("closed_trade_expectancy")})

    status = "PASS"
    if any(a.get("severity") == "WARN" for a in alerts):
        status = "WARN"
    if any(a.get("severity") == "FAIL" for a in alerts):
        status = "FAIL"

    return {
        "generated_at": utc_now_iso(),
        "status": status,
        "cost_model": cost_model,
        "expected_backtest_reference": expected,
        "paper_observed": {
            "return_pct": equity.get("return_pct", 0.0),
            "max_drawdown_pct": equity.get("max_observed_drawdown_pct", 0.0),
            "closed_trades": positions.get("closed", 0),
            "expectancy": positions.get("expectancy", 0.0),
            "no_signal_ratio_pct": signals.get("no_signal_ratio_pct", 0.0),
            "exchange_error_rate_pct": errors.get("exchange_error_rate_pct", 0.0),
        },
        "thresholds": {
            "drawdown_warn_pct": round(dd_warn_threshold, 4),
            "minimum_closed_trades_for_expectancy_check": 10,
            "no_signal_warn_ratio_pct": 98.0,
            "exchange_error_warn_rate_pct": 10.0,
        },
        "alerts": alerts,
    }


def _fmt_money(value: Any) -> str:
    return f"{_safe_float(value):,.2f}"


def _fmt_pct(value: Any) -> str:
    return f"{_safe_float(value):.2f}%"


def _status_class(status: str) -> str:
    status = str(status or "").upper()
    if status == "PASS":
        return "ok"
    if status == "FAIL":
        return "bad"
    return "warn"


def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_dashboard_html(performance: dict[str, Any], drift: dict[str, Any], lifecycle: dict[str, Any]) -> str:
    engine = performance.get("engine", {}) if isinstance(performance.get("engine"), dict) else {}
    equity = performance.get("equity", {}) if isinstance(performance.get("equity"), dict) else {}
    cycles = performance.get("cycles", {}) if isinstance(performance.get("cycles"), dict) else {}
    signals = performance.get("signals", {}) if isinstance(performance.get("signals"), dict) else {}
    signal_diagnostics = performance.get("signal_diagnostics", {}) if isinstance(performance.get("signal_diagnostics"), dict) else {}
    signal_diagnostics_backfill = performance.get("signal_diagnostics_backfill", {}) if isinstance(performance.get("signal_diagnostics_backfill"), dict) else {}
    shadow_unlock = performance.get("shadow_unlock", {}) if isinstance(performance.get("shadow_unlock"), dict) else {}
    unlock_rejection = performance.get("unlock_rejection_analysis", {}) if isinstance(performance.get("unlock_rejection_analysis"), dict) else {}
    crypto_scenario = performance.get("crypto_scenario", {}) if isinstance(performance.get("crypto_scenario"), dict) else {}
    orders = performance.get("orders", {}) if isinstance(performance.get("orders"), dict) else {}
    positions = performance.get("positions", {}) if isinstance(performance.get("positions"), dict) else {}
    position_monitor = performance.get("position_monitor", {}) if isinstance(performance.get("position_monitor"), dict) else {}
    monitor_positions = position_monitor.get("positions", []) if isinstance(position_monitor.get("positions"), list) else []
    errors = performance.get("errors", {}) if isinstance(performance.get("errors"), dict) else {}
    by_asset = performance.get("by_asset", {}) if isinstance(performance.get("by_asset"), dict) else {}
    recent = performance.get("recent_events", []) if isinstance(performance.get("recent_events"), list) else []
    alerts = drift.get("alerts", []) if isinstance(drift.get("alerts"), list) else []

    asset_rows = []
    for symbol, row in sorted(by_asset.items()):
        if not isinstance(row, dict):
            continue
        asset_rows.append([
            symbol,
            row.get("scanned", 0),
            row.get("signals", 0),
            row.get("orders_submitted", 0),
            row.get("positions_closed", 0),
            _fmt_pct(row.get("no_signal_ratio_pct", 0.0)),
            row.get("errors", 0),
            _fmt_money(row.get("closed_trade_expectancy", 0.0)),
        ])

    event_rows = []
    for event in recent[-12:][::-1]:
        if not isinstance(event, dict):
            continue
        detail_parts = []
        for key in ("cycle_id", "symbol", "reason", "error", "orders", "signals", "no_signal"):
            if key in event and event.get(key) not in (None, ""):
                detail_parts.append(f"{key}={event.get(key)}")
        event_rows.append([event.get("ts", ""), event.get("event_type", ""), " | ".join(detail_parts)])

    monitor_rows = []
    for p in monitor_positions:
        if not isinstance(p, dict):
            continue
        monitor_rows.append([
            p.get("symbol", ""),
            p.get("side", ""),
            p.get("reason", "-"),
            _fmt_money(p.get("entry_price", 0.0)),
            _fmt_money(p.get("mark_price", 0.0)),
            _fmt_money(p.get("stop_loss", 0.0)),
            _fmt_money(p.get("take_profit_1", 0.0)),
            _fmt_money(p.get("take_profit_2", 0.0)),
            _fmt_money(p.get("unrealized_pnl", 0.0)),
            _fmt_pct(p.get("unrealized_pnl_pct", 0.0)),
        ])

    alert_rows = []
    for alert in alerts:
        if isinstance(alert, dict):
            alert_rows.append([alert.get("severity", ""), alert.get("code", ""), json.dumps({k: v for k, v in alert.items() if k not in {"severity", "code"}}, ensure_ascii=False)])

    diagnostic_filter_rows = []
    if isinstance(signal_diagnostics, dict):
        for name, count in (signal_diagnostics.get("dominant_filters") or {}).items():
            diagnostic_filter_rows.append([name, count])
    diagnostic_asset_rows = []
    if isinstance(signal_diagnostics, dict):
        by_diag_asset = signal_diagnostics.get("by_asset", {}) if isinstance(signal_diagnostics.get("by_asset"), dict) else {}
        for symbol, row in sorted(by_diag_asset.items()):
            if isinstance(row, dict):
                diagnostic_asset_rows.append([
                    symbol,
                    row.get("scans", 0),
                    row.get("near_candidates", 0),
                    row.get("exploratory_candidates", 0),
                    row.get("meta_reached", 0),
                    f"{_safe_float(row.get('max_ai_prob'), 0.0):.2f}",
                    f"{_safe_float(row.get('max_setup_quality'), 0.0):.2f}",
                    f"{_safe_float(row.get('max_abs_technical_score'), 0.0):.2f}",
                ])

    shadow_profile_rows = []
    if isinstance(shadow_unlock, dict):
        for name, row in (shadow_unlock.get("profiles") or {}).items():
            if isinstance(row, dict):
                shadow_profile_rows.append([
                    name,
                    row.get("simulated_rows", 0),
                    _fmt_pct(row.get("win_rate_pct", 0.0)),
                    f"{_safe_float(row.get('expectancy_r'), 0.0):.3f}R",
                    f"{_safe_float(row.get('total_r'), 0.0):.3f}R",
                    json.dumps(row.get("outcomes", {}), ensure_ascii=False),
                ])

    unlock_rejection_rows = []
    if isinstance(unlock_rejection, dict):
        decision = unlock_rejection.get("decision", {}) if isinstance(unlock_rejection.get("decision"), dict) else {}
        counts = unlock_rejection.get("counts", {}) if isinstance(unlock_rejection.get("counts"), dict) else {}
        unlock_rejection_rows.append([
            unlock_rejection.get("status", "NA"),
            decision.get("status", "NA"),
            counts.get("paper_unlock_evaluated", 0),
            counts.get("btc_evaluated", 0),
            counts.get("paper_unlock_accepted_evaluations", 0),
            decision.get("dominant_btc_reason", "-"),
            decision.get("next_patch", "-"),
        ])

    crypto_scenario_rows = []
    crypto_btc_rows = []
    if isinstance(crypto_scenario, dict):
        decision = crypto_scenario.get("decision", {}) if isinstance(crypto_scenario.get("decision"), dict) else {}
        counts = crypto_scenario.get("counts", {}) if isinstance(crypto_scenario.get("counts"), dict) else {}
        crypto_scenario_rows.append([
            crypto_scenario.get("status", "NA"),
            decision.get("status", "NA"),
            counts.get("scenario_events", 0),
            counts.get("btc_scenario_events", 0),
            decision.get("action", "-"),
            decision.get("next_patch", "-"),
        ])
        btc = crypto_scenario.get("btc_focus", {}) if isinstance(crypto_scenario.get("btc_focus"), dict) else {}
        crypto_btc_rows.append([
            json.dumps(btc.get("scenarios", {}), ensure_ascii=False),
            json.dumps(btc.get("directional_bias", {}), ensure_ascii=False),
            json.dumps(btc.get("scenario_alignment", {}), ensure_ascii=False),
            json.dumps(btc.get("dominant_filters", {}), ensure_ascii=False),
        ])

    css = """
    :root { color-scheme: dark; }
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #0f172a; color: #e5e7eb; }
    header { padding: 22px 28px; border-bottom: 1px solid #334155; background: #111827; }
    h1 { margin: 0; font-size: 24px; letter-spacing: .04em; }
    h2 { margin: 0 0 12px; font-size: 16px; color: #cbd5e1; }
    .sub { color: #94a3b8; margin-top: 6px; }
    main { padding: 22px 28px 40px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 18px; }
    .card { background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; box-shadow: 0 8px 24px rgba(0,0,0,.22); }
    .metric { font-size: 24px; font-weight: 700; margin-top: 8px; }
    .label { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .ok { color: #86efac; } .warn { color: #fde68a; } .bad { color: #fca5a5; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid #334155; text-align: left; padding: 8px 6px; vertical-align: top; }
    th { color: #cbd5e1; font-weight: 600; }
    .section { margin-top: 18px; }
    .mono { font-family: Consolas, Menlo, monospace; }
    """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="20">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProgettoTR Paper Dashboard</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>PROGETTOTR PAPER ENGINE</h1>
  <div class="sub">Auto-refresh 20s | generated {escape(str(performance.get('generated_at', '')))}</div>
</header>
<main>
  <div class="grid">
    <div class="card"><div class="label">Performance</div><div class="metric {_status_class(str(performance.get('status')))}">{escape(str(performance.get('status')))}</div></div>
    <div class="card"><div class="label">Drift</div><div class="metric {_status_class(str(drift.get('status')))}">{escape(str(drift.get('status')))}</div></div>
    <div class="card"><div class="label">Lifecycle</div><div class="metric {_status_class(str(lifecycle.get('status')))}">{escape(str(lifecycle.get('status')))}</div></div>
    <div class="card"><div class="label">Mode</div><div class="metric">{escape(str(engine.get('mode', 'paper')).upper())}</div></div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Balance</div><div class="metric">{_fmt_money(equity.get('balance'))}</div></div>
    <div class="card"><div class="label">Equity</div><div class="metric">{_fmt_money(equity.get('equity'))}</div></div>
    <div class="card"><div class="label">Return</div><div class="metric">{_fmt_pct(equity.get('return_pct'))}</div></div>
    <div class="card"><div class="label">Drawdown</div><div class="metric">{_fmt_pct(equity.get('max_observed_drawdown_pct'))}</div></div>
    <div class="card"><div class="label">Open Positions</div><div class="metric">{escape(str(positions.get('open', 0)))}</div></div>
    <div class="card"><div class="label">No-signal Ratio</div><div class="metric">{_fmt_pct(signals.get('no_signal_ratio_pct'))}</div></div>
  </div>

  <div class="card section">
    <h2>Runtime Summary</h2>
    {_render_table(['Field','Value'], [
        ['Assets', ', '.join(map(str, engine.get('symbols', [])))],
        ['Timeframe', engine.get('timeframe', '')],
        ['Cost model', engine.get('cost_model', '')],
        ['Telegram proactive', (engine.get('telegram_proactive') or {}).get('enabled', '-')],
        ['AI debug', (engine.get('operational_console') or {}).get('ai_debug', '-')],
        ['Cycle seq', engine.get('cycle_seq', '')],
        ['Completed cycles', cycles.get('completed', 0)],
        ['Avg cycle seconds', cycles.get('avg_cycle_seconds', 0.0)],
        ['Orders submitted / filled / rejected', f"{orders.get('submitted',0)} / {orders.get('filled',0)} / {orders.get('rejected',0)}"],
        ['Closed positions / win rate / expectancy', f"{positions.get('closed',0)} / {_fmt_pct(positions.get('win_rate_pct'))} / {_fmt_money(positions.get('expectancy'))}"],
        ['Exchange errors / rate', f"{errors.get('symbol_errors',0)} / {_fmt_pct(errors.get('exchange_error_rate_pct'))}"],
        ['Kill switch', engine.get('kill_switch', False)],
        ['Paused', engine.get('is_paused', False)],
        ['Last cycle', engine.get('last_cycle_time', '')],
    ])}
  </div>

  <div class="card section">
    <h2>Open Position Monitor</h2>
    {_render_table(['Asset','Side','Reason','Entry','Mark','SL','TP1','TP2','uPnL','uPnL %'], monitor_rows or [['-','-','No open paper positions.','-','-','-','-','-','-','-']])}
  </div>

  <div class="card section">
    <h2>Asset Scan Table</h2>
    {_render_table(['Asset','Scanned','Signals','Orders','Closed','No-signal','Errors','Expectancy'], asset_rows or [['-',0,0,0,0,'0.00%',0,'0.00']])}
  </div>

  <div class="card section">
    <h2>Signal Diagnostics</h2>
    {_render_table(['Metric','Value'], [
        ['Status', signal_diagnostics.get('status', 'NA') if isinstance(signal_diagnostics, dict) else 'NA'],
        ['Diagnostic-only', signal_diagnostics.get('diagnostic_only', True) if isinstance(signal_diagnostics, dict) else True],
        ['Strategy changed', signal_diagnostics.get('strategy_changed', False) if isinstance(signal_diagnostics, dict) else False],
        ['Backfill inferred diagnostics', (signal_diagnostics_backfill.get('counts') or {}).get('inferred_diagnostics', 0) if isinstance(signal_diagnostics_backfill, dict) else 0],
        ['Backfill combined diagnostics', (signal_diagnostics_backfill.get('counts') or {}).get('combined_diagnostics', 0) if isinstance(signal_diagnostics_backfill, dict) else 0],
        ['Diagnostics / near / exploratory', f"{signals.get('diagnostics',0)} / {signals.get('near_candidates',0)} / {signals.get('exploratory_candidates',0)}"],
    ])}
    <h2 style="margin-top:16px">Dominant Filters</h2>
    {_render_table(['Filter','Count'], diagnostic_filter_rows or [['-','No diagnostics yet.']])}
    <h2 style="margin-top:16px">Diagnostic Asset Table</h2>
    {_render_table(['Asset','Scans','Near','Exploratory','Meta reached','Max AI %','Max Quality','Max |Tech|'], diagnostic_asset_rows or [['-',0,0,0,0,'0.00','0.00','0.00']])}
  </div>

  <div class="card section">
    <h2>Shadow Unlock Simulation</h2>
    {_render_table(['Metric','Value'], [
        ['Status', shadow_unlock.get('status', 'NA') if isinstance(shadow_unlock, dict) else 'NA'],
        ['Shadow-only', shadow_unlock.get('shadow_only', True) if isinstance(shadow_unlock, dict) else True],
        ['Strategy changed', shadow_unlock.get('strategy_changed', False) if isinstance(shadow_unlock, dict) else False],
        ['Shadow rows total', (shadow_unlock.get('counts') or {}).get('shadow_rows_total', 0) if isinstance(shadow_unlock, dict) else 0],
        ['Model', (shadow_unlock.get('simulation_model') or {}).get('price_source', '-') if isinstance(shadow_unlock, dict) else '-'],
    ])}
    <h2 style="margin-top:16px">Shadow Profiles</h2>
    {_render_table(['Profile','Rows','Win rate','Expectancy','Total R','Outcomes'], shadow_profile_rows or [['-','0','0.00%','0.000R','0.000R','No shadow candidates yet.']])}
  </div>

  <div class="card section">
    <h2>Unlock Rejection Analysis</h2>
    {_render_table(['Report','Decision','Eval','BTC Eval','Accepted','BTC Dominant Reason','Next'], unlock_rejection_rows or [['NA','NA',0,0,0,'-','No unlock rejection report yet.']])}
  </div>

  <div class="card section">
    <h2>Crypto Intraday Scenario</h2>
    {_render_table(['Report','Decision','Events','BTC Events','Action','Next'], crypto_scenario_rows or [['NA','NA',0,0,'-','No crypto scenario report yet.']])}
    <h2 style="margin-top:16px">BTC Scenario Focus</h2>
    {_render_table(['Scenarios','Directional bias','Alignment','Dominant filters'], crypto_btc_rows or [['{}','{}','{}','{}']])}
  </div>

  <div class="card section">
    <h2>Drift Alerts</h2>
    {_render_table(['Severity','Code','Details'], alert_rows or [['PASS','NONE','No active warning alerts.']])}
  </div>

  <div class="card section">
    <h2>Recent Events</h2>
    {_render_table(['Timestamp','Event','Details'], event_rows or [['-','-','No events yet.']])}
  </div>
</main>
</body>
</html>"""


def write_performance_artifacts(data_dir: str | Path) -> dict[str, Any]:
    paths = PaperPerformancePaths(Path(data_dir))
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    lifecycle = _read_json(paths.lifecycle_path) or build_lifecycle_report(paths.data_dir)
    try:
        from config import Config
        rejection_enabled = bool(getattr(Config, "PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED", True))
    except Exception:
        rejection_enabled = True
    if rejection_enabled:
        try:
            from core.paper_unlock_rejection_analysis import write_unlock_rejection_report
            unlock_rejection = write_unlock_rejection_report(paths.data_dir)
        except Exception as exc:
            unlock_rejection = {"status": "FAIL", "error": str(exc)}
    else:
        unlock_rejection = {"status": "DISABLED"}
    try:
        from config import Config
        scenario_enabled = bool(getattr(Config, "PAPER_CRYPTO_SCENARIO_ENABLED", True))
    except Exception:
        scenario_enabled = True
    if scenario_enabled:
        try:
            from core.crypto_intraday_scenario import write_crypto_scenario_report
            crypto_scenario = write_crypto_scenario_report(paths.data_dir)
        except Exception as exc:
            crypto_scenario = {"status": "FAIL", "error": str(exc)}
    else:
        crypto_scenario = {"status": "DISABLED"}
    try:
        from config import Config
        pattern_enabled = bool(getattr(Config, "PAPER_CANDLESTICK_PATTERNS_ENABLED", True))
    except Exception:
        pattern_enabled = True
    if pattern_enabled:
        try:
            from core.candlestick_patterns import write_candlestick_pattern_report
            candlestick_patterns = write_candlestick_pattern_report(paths.data_dir)
        except Exception as exc:
            candlestick_patterns = {"status": "FAIL", "error": str(exc)}
    else:
        candlestick_patterns = {"status": "DISABLED"}
    try:
        from config import Config
        pcs_enabled = bool(getattr(Config, "PATTERN_CONDITIONED_SHADOW_ENABLED", True))
    except Exception:
        pcs_enabled = True
    if pcs_enabled:
        try:
            from core.pattern_conditioned_shadow import write_pattern_conditioned_shadow_report
            pattern_conditioned_shadow = write_pattern_conditioned_shadow_report(paths.data_dir)
        except Exception as exc:
            pattern_conditioned_shadow = {"status": "FAIL", "error": str(exc)}
    else:
        pattern_conditioned_shadow = {"status": "DISABLED"}
    try:
        from config import Config
        spc_enabled = bool(getattr(Config, "SCENARIO_PATTERN_CALIBRATION_ENABLED", True))
    except Exception:
        spc_enabled = True
    if spc_enabled:
        try:
            from core.scenario_pattern_calibration import write_scenario_pattern_calibration_report
            scenario_pattern_calibration = write_scenario_pattern_calibration_report(paths.data_dir)
        except Exception as exc:
            scenario_pattern_calibration = {"status": "FAIL", "error": str(exc)}
    else:
        scenario_pattern_calibration = {"status": "DISABLED"}
    try:
        from config import Config
        msm_enabled = bool(getattr(Config, "MARKET_STRUCTURE_MAP_ENABLED", True))
    except Exception:
        msm_enabled = True
    if msm_enabled:
        try:
            from core.market_structure_map import write_market_structure_map_report
            market_structure_map = write_market_structure_map_report(paths.data_dir)
        except Exception as exc:
            market_structure_map = {"status": "FAIL", "error": str(exc)}
    else:
        market_structure_map = {"status": "DISABLED"}
    try:
        from config import Config
        css_enabled = bool(getattr(Config, "CALIBRATED_STRUCTURE_SHADOW_ENABLED", True))
    except Exception:
        css_enabled = True
    if css_enabled:
        try:
            from core.calibrated_structure_shadow import write_calibrated_structure_shadow_report
            calibrated_structure_shadow = write_calibrated_structure_shadow_report(paths.data_dir)
        except Exception as exc:
            calibrated_structure_shadow = {"status": "FAIL", "error": str(exc)}
    else:
        calibrated_structure_shadow = {"status": "DISABLED"}
    try:
        from config import Config
        sfd_enabled = bool(getattr(Config, "STRUCTURE_FILTER_DIAGNOSTICS_ENABLED", True))
    except Exception:
        sfd_enabled = True
    if sfd_enabled:
        try:
            from core.structure_filter_diagnostics import write_structure_filter_diagnostics_report
            structure_filter_diagnostics = write_structure_filter_diagnostics_report(paths.data_dir)
        except Exception as exc:
            structure_filter_diagnostics = {"status": "FAIL", "error": str(exc)}
    else:
        structure_filter_diagnostics = {"status": "DISABLED"}
    try:
        from config import Config
        scr_enabled = bool(getattr(Config, "STRUCTURE_CONTEXT_REPAIR_ENABLED", True))
    except Exception:
        scr_enabled = True
    if scr_enabled:
        try:
            from core.structure_context_repair import write_structure_context_repair_report
            structure_context_repair = write_structure_context_repair_report(paths.data_dir)
        except Exception as exc:
            structure_context_repair = {"status": "FAIL", "error": str(exc)}
    else:
        structure_context_repair = {"status": "DISABLED"}
    try:
        from config import Config
        rsv_enabled = bool(getattr(Config, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED", True))
    except Exception:
        rsv_enabled = True
    if rsv_enabled:
        try:
            from core.repaired_structure_shadow_validation import write_repaired_structure_shadow_validation_report
            repaired_structure_shadow_validation = write_repaired_structure_shadow_validation_report(paths.data_dir)
        except Exception as exc:
            repaired_structure_shadow_validation = {"status": "FAIL", "error": str(exc)}
    else:
        repaired_structure_shadow_validation = {"status": "DISABLED"}
    try:
        from config import Config
        irv_enabled = bool(getattr(Config, "INDEPENDENT_REPAIRED_VALIDATION_ENABLED", True))
    except Exception:
        irv_enabled = True
    if irv_enabled:
        try:
            from core.independent_repaired_validation import write_independent_repaired_validation_report
            independent_repaired_validation = write_independent_repaired_validation_report(paths.data_dir)
        except Exception as exc:
            independent_repaired_validation = {"status": "FAIL", "error": str(exc)}
    else:
        independent_repaired_validation = {"status": "DISABLED"}
    try:
        from config import Config
        pur_enabled = bool(getattr(Config, "PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED", True))
    except Exception:
        pur_enabled = True
    if pur_enabled:
        try:
            from core.paper_unlock_profile_refinement import write_paper_unlock_profile_refinement_report
            paper_unlock_profile_refinement = write_paper_unlock_profile_refinement_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_profile_refinement = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_profile_refinement = {"status": "DISABLED"}

    try:
        from config import Config
        ped_enabled = bool(getattr(Config, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED", True))
    except Exception:
        ped_enabled = True
    if ped_enabled:
        try:
            from core.paper_unlock_experiment_design import write_paper_unlock_experiment_design_report
            paper_unlock_experiment_design = write_paper_unlock_experiment_design_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_experiment_design = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_experiment_design = {"status": "DISABLED"}

    try:
        from config import Config
        psd_enabled = bool(getattr(Config, "PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED", True))
    except Exception:
        psd_enabled = True
    if psd_enabled:
        try:
            from core.paper_unlock_shadow_dry_run import write_paper_unlock_shadow_dry_run_report
            paper_unlock_shadow_dry_run = write_paper_unlock_shadow_dry_run_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_shadow_dry_run = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_shadow_dry_run = {"status": "DISABLED"}

    try:
        from config import Config
        psrc_enabled = bool(getattr(Config, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED", True))
    except Exception:
        psrc_enabled = True
    if psrc_enabled:
        try:
            from core.paper_unlock_shadow_rate_calibration import write_paper_unlock_shadow_rate_calibration_report
            paper_unlock_shadow_rate_calibration = write_paper_unlock_shadow_rate_calibration_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_shadow_rate_calibration = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_shadow_rate_calibration = {"status": "DISABLED"}

    try:
        from config import Config
        pbc_enabled = bool(getattr(Config, "PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED", True))
    except Exception:
        pbc_enabled = True
    if pbc_enabled:
        try:
            from core.paper_unlock_bounded_cadence import write_paper_unlock_bounded_cadence_report
            paper_unlock_bounded_cadence = write_paper_unlock_bounded_cadence_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_bounded_cadence = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_bounded_cadence = {"status": "DISABLED"}


    try:
        from config import Config
        pssr_enabled = bool(getattr(Config, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED", True))
    except Exception:
        pssr_enabled = True
    if pssr_enabled:
        try:
            from core.paper_unlock_shadow_stability_review import write_paper_unlock_shadow_stability_review_report
            paper_unlock_shadow_stability_review = write_paper_unlock_shadow_stability_review_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_shadow_stability_review = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_shadow_stability_review = {"status": "DISABLED"}

    try:
        from config import Config
        pad_enabled = bool(getattr(Config, "PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED", True))
    except Exception:
        pad_enabled = True
    if pad_enabled:
        try:
            from core.paper_unlock_activation_draft import write_paper_unlock_activation_draft_report
            paper_unlock_activation_draft = write_paper_unlock_activation_draft_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_activation_draft = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_activation_draft = {"status": "DISABLED"}

    try:
        from config import Config
        psd_enabled = bool(getattr(Config, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED", True))
    except Exception:
        psd_enabled = True
    if psd_enabled:
        try:
            from core.paper_unlock_experiment_switch_draft import write_paper_unlock_experiment_switch_draft_report
            paper_unlock_experiment_switch_draft = write_paper_unlock_experiment_switch_draft_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_experiment_switch_draft = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_experiment_switch_draft = {"status": "DISABLED"}


    try:
        from config import Config
        pms_enabled = bool(getattr(Config, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED", True))
    except Exception:
        pms_enabled = True
    if pms_enabled:
        try:
            from core.paper_unlock_manual_switch_preflight import write_paper_unlock_manual_switch_preflight_report
            paper_unlock_manual_switch_preflight = write_paper_unlock_manual_switch_preflight_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_manual_switch_preflight = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_manual_switch_preflight = {"status": "DISABLED"}

    try:
        from config import Config
        pma_enabled = bool(getattr(Config, "PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ENABLED", True))
    except Exception:
        pma_enabled = True
    if pma_enabled:
        try:
            from core.paper_unlock_manual_activation_patch import write_paper_unlock_manual_activation_patch_report
            paper_unlock_manual_activation_patch = write_paper_unlock_manual_activation_patch_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_manual_activation_patch = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_manual_activation_patch = {"status": "DISABLED"}

    try:
        from config import Config
        pfe_enabled = bool(getattr(Config, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED", True))
    except Exception:
        pfe_enabled = True
    if pfe_enabled:
        try:
            from core.paper_unlock_final_enable_preflight import write_paper_unlock_final_enable_preflight_report
            paper_unlock_final_enable_preflight = write_paper_unlock_final_enable_preflight_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_final_enable_preflight = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_final_enable_preflight = {"status": "DISABLED"}

    try:
        from config import Config
        pge_enabled = bool(getattr(Config, "PAPER_UNLOCK_GUARDED_ENABLE_ENABLED", True))
    except Exception:
        pge_enabled = True
    if pge_enabled:
        try:
            from core.paper_unlock_guarded_enable import write_paper_unlock_guarded_enable_report
            paper_unlock_guarded_enable = write_paper_unlock_guarded_enable_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_guarded_enable = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_guarded_enable = {"status": "DISABLED"}

    try:
        from config import Config
        pra_enabled = bool(getattr(Config, "PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED", True))
    except Exception:
        pra_enabled = True
    if pra_enabled:
        try:
            from core.paper_unlock_runtime_audit import write_paper_unlock_runtime_audit_report
            paper_unlock_runtime_audit = write_paper_unlock_runtime_audit_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_runtime_audit = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_runtime_audit = {"status": "DISABLED"}

    try:
        from config import Config
        prb_enabled = bool(getattr(Config, "PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED", True))
    except Exception:
        prb_enabled = True
    if prb_enabled:
        try:
            from core.paper_unlock_routing_bridge import write_paper_unlock_routing_bridge_report
            paper_unlock_routing_bridge = write_paper_unlock_routing_bridge_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_routing_bridge = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_routing_bridge = {"status": "DISABLED"}

    try:
        from config import Config
        pca_enabled = bool(getattr(Config, "PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED", True))
    except Exception:
        pca_enabled = True
    if pca_enabled:
        try:
            from core.paper_unlock_candidate_audit import write_paper_unlock_candidate_audit_report
            paper_unlock_candidate_audit = write_paper_unlock_candidate_audit_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_candidate_audit = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_candidate_audit = {"status": "DISABLED"}

    try:
        from config import Config
        phr_enabled = bool(getattr(Config, "PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED", True))
    except Exception:
        phr_enabled = True
    if phr_enabled:
        try:
            from core.paper_unlock_handoff_dry_run import write_paper_unlock_handoff_dry_run_report
            paper_unlock_handoff_dry_run = write_paper_unlock_handoff_dry_run_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_handoff_dry_run = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_handoff_dry_run = {"status": "DISABLED"}

    try:
        from config import Config
        pse_enabled = bool(getattr(Config, "PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED", True))
    except Exception:
        pse_enabled = True
    if pse_enabled:
        try:
            from core.paper_unlock_supervised_execution import write_paper_unlock_supervised_execution_report
            paper_unlock_supervised_execution = write_paper_unlock_supervised_execution_report(paths.data_dir)
        except Exception as exc:
            paper_unlock_supervised_execution = {"status": "FAIL", "error": str(exc)}
    else:
        paper_unlock_supervised_execution = {"status": "DISABLED"}
    performance = build_performance_report(paths.data_dir)
    drift = build_drift_report(paths.data_dir, performance)
    paths.performance_path.write_text(json.dumps(performance, indent=2, sort_keys=True), encoding="utf-8")
    paths.drift_path.write_text(json.dumps(drift, indent=2, sort_keys=True), encoding="utf-8")
    paths.dashboard_path.write_text(build_dashboard_html(performance, drift, lifecycle), encoding="utf-8")
    return {"performance": performance, "drift": drift, "dashboard_path": str(paths.dashboard_path), "unlock_rejection": unlock_rejection, "crypto_scenario": crypto_scenario, "candlestick_patterns": candlestick_patterns, "pattern_conditioned_shadow": pattern_conditioned_shadow, "scenario_pattern_calibration": scenario_pattern_calibration, "market_structure_map": market_structure_map, "calibrated_structure_shadow": calibrated_structure_shadow, "structure_filter_diagnostics": structure_filter_diagnostics, "structure_context_repair": structure_context_repair, "repaired_structure_shadow_validation": repaired_structure_shadow_validation, "independent_repaired_validation": independent_repaired_validation, "paper_unlock_profile_refinement": paper_unlock_profile_refinement, "paper_unlock_experiment_design": paper_unlock_experiment_design, "paper_unlock_shadow_dry_run": paper_unlock_shadow_dry_run, "paper_unlock_shadow_rate_calibration": paper_unlock_shadow_rate_calibration, "paper_unlock_bounded_cadence": paper_unlock_bounded_cadence, "paper_unlock_shadow_stability_review": paper_unlock_shadow_stability_review, "paper_unlock_activation_draft": paper_unlock_activation_draft, "paper_unlock_experiment_switch_draft": paper_unlock_experiment_switch_draft, "paper_unlock_manual_switch_preflight": paper_unlock_manual_switch_preflight, "paper_unlock_manual_activation_patch": paper_unlock_manual_activation_patch, "paper_unlock_final_enable_preflight": paper_unlock_final_enable_preflight, "paper_unlock_guarded_enable": paper_unlock_guarded_enable, "paper_unlock_runtime_audit": paper_unlock_runtime_audit, "paper_unlock_routing_bridge": paper_unlock_routing_bridge, "paper_unlock_candidate_audit": paper_unlock_candidate_audit, "paper_unlock_handoff_dry_run": paper_unlock_handoff_dry_run, "paper_unlock_supervised_execution": paper_unlock_supervised_execution}
