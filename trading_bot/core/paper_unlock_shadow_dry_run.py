"""Prompt 29.4.4e paper-only shadow experiment dry-run harness.

This module takes the calibrated paper-only experiment design from Prompt
29.4.4d and runs it in a historical/runtime-compatible *shadow harness*.
It does not submit paper orders, does not open positions, does not enable
live/testnet execution, and does not mutate risk or thresholds.

The report is ``paper_unlock_shadow_dry_run_report.json``.  Its purpose is to
prove that the future paper experiment can be audited with entry selection,
rate limits and abort criteria before any execution path is activated.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _collect_historical_rows, _safe_float, _safe_int, _summarize_rows
from core.independent_repaired_validation import _parse_dt, _sort_rows, _target_map_score_65_79
from core.paper_unlock_experiment_design import (
    EXPERIMENT_NAME,
    REPORT_NAME as EXPERIMENT_DESIGN_REPORT_NAME,
    PaperUnlockExperimentDesignSettings,
)
from core.paper_unlock_profile_refinement import PROFILE_NAME
from core.repaired_structure_shadow_validation import _is_conflict, _is_entry_state, _is_no_structure, _is_wait
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_shadow_dry_run_report.json"
PROMPT_ID = "29.4.4e"
HARNESS_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_DRY_RUN"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockShadowDryRunSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_variant_candidates: int = 50
    min_shadow_entries: int = 20
    min_shadow_expectancy_r: float = 0.05
    max_shadow_loss_rate_pct: float = 50.0
    max_shadow_time_exit_rate_pct: float = 60.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    harness_name: str = HARNESS_NAME
    dry_run_max_positions: int = 1
    dry_run_risk_per_trade_pct: float = 0.0025
    dry_run_max_daily_entries: int = 1
    dry_run_max_weekly_entries: int = 5
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0
    require_experiment_design_ready: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockShadowDryRunSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_ROWS_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_EVAL_STRIDE", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_STRUCTURE_WINDOW_ROWS", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_VARIANT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_shadow_entries=max(5, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_ENTRIES", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_RUNTIME_SHADOW_MIN_CANDIDATES", 20)), 20)),
            min_shadow_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_EXPECTANCY_R", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_RUNTIME_EXPECTANCY_R", 0.05)), 0.05),
            max_shadow_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_LOSS_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_RUNTIME_LOSS_RATE_PCT", 50.0)), 50.0),
            max_shadow_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_PROFILE_NAME", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROFILE_NAME", PROFILE_NAME)) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_EXPERIMENT_NAME", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_EXPERIMENT_NAME", EXPERIMENT_NAME)) or EXPERIMENT_NAME),
            harness_name=str(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_HARNESS_NAME", HARNESS_NAME) or HARNESS_NAME),
            dry_run_max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_POSITIONS", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_POSITIONS", 1)), 1)),
            dry_run_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_RISK_PER_TRADE_PCT", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_RISK_PER_TRADE_PCT", 0.0025)), 0.0025)),
            dry_run_max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_DAILY_ENTRIES", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_DAILY_ENTRIES", 1)), 1)),
            dry_run_max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_WEEKLY_ENTRIES", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_WEEKLY_ENTRIES", 5)), 5)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_CONSECUTIVE_LOSSES", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_CONSECUTIVE_LOSSES", 3)), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_DRAWDOWN_PCT", getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_DRAWDOWN_PCT", 1.0)), 1.0)),
            require_experiment_design_ready=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_REQUIRE_EXPERIMENT_READY", True)),
        )

    def experiment_settings(self) -> PaperUnlockExperimentDesignSettings:
        return PaperUnlockExperimentDesignSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
            profile_name=self.profile_name,
            experiment_name=self.experiment_name,
            proposed_max_positions=self.dry_run_max_positions,
            proposed_risk_per_trade_pct=self.dry_run_risk_per_trade_pct,
            proposed_max_daily_entries=self.dry_run_max_daily_entries,
            proposed_max_weekly_entries=self.dry_run_max_weekly_entries,
            proposed_runtime_shadow_min_candidates=self.min_shadow_entries,
            proposed_min_runtime_expectancy_r=self.min_shadow_expectancy_r,
            proposed_max_runtime_loss_rate_pct=self.max_shadow_loss_rate_pct,
            proposed_abort_max_consecutive_losses=self.abort_max_consecutive_losses,
            proposed_abort_max_drawdown_pct=self.abort_max_drawdown_pct,
        )

    def independent_settings(self):
        return self.experiment_settings().independent_settings()

    def calibrated_settings(self):
        return self.experiment_settings().calibrated_settings()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"status": "READ_ERROR", "error": str(exc)}


def _experiment_design_guard(experiment_report: dict[str, Any], settings: PaperUnlockShadowDryRunSettings) -> dict[str, Any]:
    if not experiment_report:
        return {
            "experiment_design_ready": False,
            "experiment_report_status": "MISSING",
            "experiment_decision_status": "MISSING",
            "reason": f"{EXPERIMENT_DESIGN_REPORT_NAME} is missing",
        }
    decision = experiment_report.get("decision", {}) if isinstance(experiment_report.get("decision"), dict) else {}
    status = str(experiment_report.get("status") or "NA")
    decision_status = str(decision.get("status") or "NA")
    profile_name = str(decision.get("profile_name") or experiment_report.get("profile_name") or "")
    experiment_name = str(decision.get("experiment_name") or experiment_report.get("experiment_name") or "")
    ready = bool(
        status == "PASS"
        and decision_status == "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC"
        and profile_name == settings.profile_name
        and experiment_name == settings.experiment_name
        and not bool(decision.get("operational_unlock_allowed", False))
        and not bool(decision.get("paper_unlock_experiment_allowed", False))
        and not bool(decision.get("paper_orders_enabled", False))
        and not bool(experiment_report.get("paper_orders_enabled", False))
        and not bool(experiment_report.get("operational_unlock_allowed", False))
    )
    return {
        "experiment_design_ready": ready,
        "experiment_report_status": status,
        "experiment_decision_status": decision_status,
        "profile_name": profile_name,
        "experiment_name": experiment_name,
        "paper_orders_enabled": bool(experiment_report.get("paper_orders_enabled", False) or decision.get("paper_orders_enabled", False)),
        "paper_unlock_experiment_allowed": bool(experiment_report.get("paper_unlock_experiment_allowed", False) or decision.get("paper_unlock_experiment_allowed", False)),
        "operational_unlock_allowed": bool(experiment_report.get("operational_unlock_allowed", False) or decision.get("operational_unlock_allowed", False)),
        "reason": "experiment design guard passed" if ready else "experiment design guard did not pass or execution flags were attempted",
    }


def _target_rows(rows: list[dict[str, Any]], settings: PaperUnlockShadowDryRunSettings) -> list[dict[str, Any]]:
    ist = settings.independent_settings()
    return [r for r in rows if _target_map_score_65_79(r, ist)]


def _entry_candidate_rows(target: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in target if _is_entry_state(r) and not _is_wait(r) and not _is_no_structure(r) and not _is_conflict(r)]


def _date_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    return dt.date().isoformat() if dt else "UNKNOWN_DATE"


def _week_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    if not dt:
        return "UNKNOWN_WEEK"
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _dry_run_select(rows: list[dict[str, Any]], settings: PaperUnlockShadowDryRunSettings) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    daily_counts: Counter[str] = Counter()
    weekly_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    for row in _sort_rows(rows):
        day = _date_key(row)
        week = _week_key(row)
        reason = ""
        if daily_counts[day] >= settings.dry_run_max_daily_entries:
            reason = "DAILY_LIMIT"
        elif weekly_counts[week] >= settings.dry_run_max_weekly_entries:
            reason = "WEEKLY_LIMIT"
        if reason:
            rejection_counts[reason] += 1
            rejected.append({**row, "dry_run_reject_reason": reason})
            continue
        daily_counts[day] += 1
        weekly_counts[week] += 1
        selected.append({**row, "dry_run_event": "SHADOW_ENTRY_ACCEPTED", "dry_run_day": day, "dry_run_week": week})
    limit_summary = {
        "max_daily_entries": settings.dry_run_max_daily_entries,
        "max_weekly_entries": settings.dry_run_max_weekly_entries,
        "days_used": len(daily_counts),
        "weeks_used": len(weekly_counts),
        "max_observed_daily_entries": max(daily_counts.values()) if daily_counts else 0,
        "max_observed_weekly_entries": max(weekly_counts.values()) if weekly_counts else 0,
        "rejection_counts": dict(rejection_counts),
    }
    return selected, rejected, limit_summary


def _outcome_is_loss(row: dict[str, Any]) -> bool:
    outcome = str(row.get("outcome") or "").upper()
    return outcome == "SL" or _safe_float(row.get("r"), 0.0) < 0.0


def _equity_curve(selected: list[dict[str, Any]], settings: PaperUnlockShadowDryRunSettings) -> dict[str, Any]:
    cumulative_r = 0.0
    peak_r = 0.0
    max_drawdown_r = 0.0
    max_drawdown_pct = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0
    curve: list[dict[str, Any]] = []
    for idx, row in enumerate(_sort_rows(selected), start=1):
        rr = _safe_float(row.get("r"), 0.0)
        cumulative_r += rr
        if cumulative_r > peak_r:
            peak_r = cumulative_r
        drawdown_r = max(0.0, peak_r - cumulative_r)
        max_drawdown_r = max(max_drawdown_r, drawdown_r)
        drawdown_pct = drawdown_r * settings.dry_run_risk_per_trade_pct * 100.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        if _outcome_is_loss(row):
            consecutive_losses += 1
        else:
            consecutive_losses = 0
        max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        curve.append({
            "n": idx,
            "datetime": row.get("datetime"),
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "outcome": row.get("outcome"),
            "r": round(rr, 6),
            "cumulative_r": round(cumulative_r, 6),
            "drawdown_r": round(drawdown_r, 6),
            "drawdown_pct": round(drawdown_pct, 6),
        })
    return {
        "entries": len(selected),
        "cumulative_r": round(cumulative_r, 6),
        "max_drawdown_r": round(max_drawdown_r, 6),
        "max_drawdown_pct": round(max_drawdown_pct, 6),
        "max_consecutive_losses": max_consecutive_losses,
        "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
        "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
        "would_abort_on_consecutive_losses": bool(max_consecutive_losses >= settings.abort_max_consecutive_losses),
        "would_abort_on_drawdown": bool(max_drawdown_pct >= settings.abort_max_drawdown_pct),
        "tail": curve[-25:],
    }


def _bucket_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(r.get(key) or "NA") for r in rows))


def _dry_run_gate(summary: dict[str, Any], equity: dict[str, Any], guard: dict[str, Any], settings: PaperUnlockShadowDryRunSettings) -> dict[str, Any]:
    entries = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 100.0)
    time_exit = _safe_float(summary.get("time_exit_rate_pct"), 100.0)
    checks = {
        "experiment_design_ready": bool(guard.get("experiment_design_ready")),
        "sample_ok": entries >= settings.min_shadow_entries,
        "expectancy_ok": expectancy >= settings.min_shadow_expectancy_r,
        "loss_rate_ok": loss <= settings.max_shadow_loss_rate_pct,
        "time_exit_ok": time_exit <= settings.max_shadow_time_exit_rate_pct,
        "consecutive_loss_guard_ok": _safe_int(equity.get("max_consecutive_losses"), 999) < settings.abort_max_consecutive_losses,
        "drawdown_guard_ok": _safe_float(equity.get("max_drawdown_pct"), 999.0) < settings.abort_max_drawdown_pct,
        "min_shadow_entries": settings.min_shadow_entries,
        "min_shadow_expectancy_r": settings.min_shadow_expectancy_r,
        "max_shadow_loss_rate_pct": settings.max_shadow_loss_rate_pct,
        "max_shadow_time_exit_rate_pct": settings.max_shadow_time_exit_rate_pct,
        "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
        "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
    }
    checks["passes_shadow_dry_run_gate"] = bool(all(checks[k] for k in [
        "experiment_design_ready",
        "sample_ok",
        "expectancy_ok",
        "loss_rate_ok",
        "time_exit_ok",
        "consecutive_loss_guard_ok",
        "drawdown_guard_ok",
    ]))
    return checks


def _event(row: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "event_type": "PAPER_EXPERIMENT_SHADOW_ENTRY_DRY_RUN",
        "event_id": f"shadow-{idx:04d}",
        "datetime": row.get("datetime"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "bucket": row.get("bucket"),
        "map_score": row.get("map_score"),
        "structure_state": row.get("structure_state"),
        "confirmation_summary": row.get("confirmation_summary"),
        "price_location": row.get("price_location"),
        "outcome": row.get("outcome"),
        "r": row.get("r"),
        "paper_order_submitted": False,
        "position_opened": False,
    }


def _decision(guard: dict[str, Any], gate: dict[str, Any], settings: PaperUnlockShadowDryRunSettings) -> dict[str, Any]:
    if settings.require_experiment_design_ready and not guard.get("experiment_design_ready"):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "29.4.4d experiment design guard is not ready; dry-run harness cannot advance.",
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "harness_name": settings.harness_name,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Re-run 29.4.4d until experiment design is ready; do not activate paper experiment.",
        }
    if gate.get("passes_shadow_dry_run_gate"):
        return {
            "status": "SHADOW_DRY_RUN_READY_DIAGNOSTIC",
            "reason": "Paper-only shadow dry-run passed readiness, rate-limit and abort-guard checks. Execution remains disabled pending a separate guarded activation patch.",
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "harness_name": settings.harness_name,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4f guarded paper-only experiment activation draft, still no live/testnet and only after explicit user approval.",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "Shadow dry-run did not pass readiness/sample/expectancy/loss/time-exit or abort guards.",
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "harness_name": settings.harness_name,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "next_patch": "Repair dry-run guard failures before any paper experiment activation.",
    }


def _settings_payload(settings: PaperUnlockShadowDryRunSettings) -> dict[str, Any]:
    return {
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "harness_name": settings.harness_name,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_shadow_entries": settings.min_shadow_entries,
        "min_shadow_expectancy_r": settings.min_shadow_expectancy_r,
        "max_shadow_loss_rate_pct": settings.max_shadow_loss_rate_pct,
        "max_shadow_time_exit_rate_pct": settings.max_shadow_time_exit_rate_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "dry_run_max_positions": settings.dry_run_max_positions,
        "dry_run_risk_per_trade_pct": settings.dry_run_risk_per_trade_pct,
        "dry_run_max_daily_entries": settings.dry_run_max_daily_entries,
        "dry_run_max_weekly_entries": settings.dry_run_max_weekly_entries,
        "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
        "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
        "require_experiment_design_ready": settings.require_experiment_design_ready,
    }


def build_paper_unlock_shadow_dry_run_report(data_dir: str | Path = "data", settings: PaperUnlockShadowDryRunSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockShadowDryRunSettings.from_config()
    experiment_report = _read_json(base / EXPERIMENT_DESIGN_REPORT_NAME)
    guard = _experiment_design_guard(experiment_report, settings)
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    target_all = _target_rows(rows, settings) if rows else []
    target_entry = _entry_candidate_rows(target_all)
    selected, rejected, limit_summary = _dry_run_select(target_entry, settings)
    source_summary = _summarize_rows(target_all) if target_all else {}
    entry_summary = _summarize_rows(target_entry) if target_entry else {}
    dry_summary = _summarize_rows(selected) if selected else {}
    equity = _equity_curve(selected, settings)
    gate = _dry_run_gate(dry_summary, equity, guard, settings)
    decision = _decision(guard, gate, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "SHADOW_DRY_RUN_READY_DIAGNOSTIC" else "WARN")
    events = [_event(row, i) for i, row in enumerate(_sort_rows(selected), start=1)]
    report = {
        "report_type": "paper_only_shadow_experiment_dry_run_harness",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "experiment_design_guard": guard,
        "shadow_dry_run_gate": gate,
        "source_target_summary": source_summary,
        "entry_candidate_summary": entry_summary,
        "shadow_selected_summary": dry_summary,
        "equity_dry_run": equity,
        "rate_limit_summary": limit_summary,
        "rejection_summary": {
            "rejected_by_rate_limits": len(rejected),
            "blocked_wait_rows": len([r for r in target_all if _is_wait(r)]),
            "blocked_no_structure_rows": len([r for r in target_all if _is_no_structure(r)]),
            "blocked_conflict_rows": len([r for r in target_all if _is_conflict(r)]),
        },
        "component_counts": {
            "selected_by_symbol": _bucket_counts(selected, "symbol"),
            "selected_by_side": _bucket_counts(selected, "side"),
            "selected_by_structure_state": _bucket_counts(selected, "structure_state"),
            "selected_by_confirmation_summary": _bucket_counts(selected, "confirmation_summary"),
            "selected_by_price_location": _bucket_counts(selected, "price_location"),
        },
        "settings": _settings_payload(settings),
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "paper_orders_enabled": False,
        "counts": {
            "scenario_pattern_evaluation_rows": _safe_int(historical.get("scenario_pattern_evaluation_rows"), 0),
            "candidate_rows_pre_structure": _safe_int(historical.get("candidate_rows_pre_structure"), 0),
            "structured_candidate_rows": len(rows),
            "source_target_rows": len(target_all),
            "entry_candidate_rows": len(target_entry),
            "shadow_selected_entries": len(selected),
            "rate_limited_rejections": len(rejected),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "by_asset": historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {},
        "shadow_events_tail": events[-25:],
        "blocked_rows_tail": [
            {
                "datetime": r.get("datetime"),
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "map_score": r.get("map_score"),
                "structure_state": r.get("structure_state"),
                "confirmation_summary": r.get("confirmation_summary"),
                "reason": r.get("dry_run_reject_reason"),
            }
            for r in rejected[-25:]
        ],
        "files": {
            "report": str(base / REPORT_NAME),
            "paper_unlock_experiment_design": str(base / EXPERIMENT_DESIGN_REPORT_NAME),
            "paper_unlock_profile_refinement": str(base / "paper_unlock_profile_refinement_report.json"),
            "independent_repaired_validation": str(base / "independent_repaired_validation_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_shadow_dry_run_report(data_dir: str | Path = "data", settings: PaperUnlockShadowDryRunSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_shadow_dry_run_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "HARNESS_NAME",
    "PaperUnlockShadowDryRunSettings",
    "build_paper_unlock_shadow_dry_run_report",
    "write_paper_unlock_shadow_dry_run_report",
]
