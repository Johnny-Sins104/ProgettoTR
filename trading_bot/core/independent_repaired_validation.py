"""Prompt 29.5.0j independent repaired validation stability guard.

Diagnostic-only guard after 29.5.0i.

29.5.0i found the first repaired validation candidate that passed aggregate
sample/expectancy/win/loss gates: ``map_score_65_79_all``.  This module does
not unlock trading.  It stress-tests that candidate with independent stability
checks before any paper-unlock refinement is considered:

- chronological walk-forward windows;
- recent holdout validation;
- asset/side concentration and stability;
- component/state decomposition of MAP_SCORE_65_79 rows;
- comparison against repaired entry-state, confirmation-only and BOS subsets.

Safety invariant: no orders, no live, no testnet, no paper unlock and no
threshold/risk mutation.  The output is
``independent_repaired_validation_report.json``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import math

from config import Config
from core.calibrated_structure_shadow import (
    CalibratedStructureShadowSettings,
    _collect_historical_rows,
    _safe_float,
    _safe_int,
    _summarize_rows,
)
from core.repaired_structure_shadow_validation import (
    RepairedStructureShadowValidationSettings,
    _is_clean,
    _is_confirmation,
    _is_directional_bos,
    _is_entry_state,
    _is_no_structure,
    _is_wait,
    _in_map_score_65_79,
)
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "independent_repaired_validation_report.json"
PROMPT_ID = "29.5.0j"
TARGET_VARIANT_NAME = "map_score_65_79_all"


@dataclass(frozen=True)
class IndependentRepairedValidationSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_variant_candidates: int = 50
    min_component_candidates: int = 10
    min_fold_candidates: int = 10
    min_holdout_candidates: int = 15
    fold_count: int = 3
    holdout_fraction: float = 0.35
    min_expectancy_r: float = 0.10
    min_win_rate_pct: float = 52.0
    max_loss_rate_pct: float = 45.0
    max_time_exit_rate_pct: float = 60.0
    min_holdout_expectancy_r: float = 0.05
    min_holdout_win_rate_pct: float = 52.0
    max_holdout_loss_rate_pct: float = 45.0
    min_positive_fold_rate_pct: float = 66.67
    max_asset_concentration_pct: float = 70.0
    max_side_concentration_pct: float = 80.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "IndependentRepairedValidationSettings":
        return cls(
            enabled=bool(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_ROWS_PER_ASSET", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_EVAL_STRIDE", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_STRUCTURE_WINDOW_ROWS", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_VARIANT_CANDIDATES", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_component_candidates=max(3, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_COMPONENT_CANDIDATES", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_COMPONENT_CANDIDATES", 10)), 10)),
            min_fold_candidates=max(3, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_FOLD_CANDIDATES", 10), 10)),
            min_holdout_candidates=max(3, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_CANDIDATES", 15), 15)),
            fold_count=max(2, _safe_int(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_FOLD_COUNT", 3), 3)),
            holdout_fraction=min(0.80, max(0.10, _safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_HOLDOUT_FRACTION", 0.35), 0.35))),
            min_expectancy_r=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_EXPECTANCY_R", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_WIN_RATE_PCT", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_LOSS_RATE_PCT", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            min_holdout_expectancy_r=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_EXPECTANCY_R", 0.05), 0.05),
            min_holdout_win_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_WIN_RATE_PCT", 52.0), 52.0),
            max_holdout_loss_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_HOLDOUT_LOSS_RATE_PCT", 45.0), 45.0),
            min_positive_fold_rate_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_POSITIVE_FOLD_RATE_PCT", 66.67), 66.67),
            max_asset_concentration_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_ASSET_CONCENTRATION_PCT", 70.0), 70.0),
            max_side_concentration_pct=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_SIDE_CONCENTRATION_PCT", 80.0), 80.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
        )

    def repaired_validation_settings(self) -> RepairedStructureShadowValidationSettings:
        return RepairedStructureShadowValidationSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            min_component_candidates=self.min_component_candidates,
            min_expectancy_r=self.min_expectancy_r,
            min_win_rate_pct=self.min_win_rate_pct,
            max_loss_rate_pct=self.max_loss_rate_pct,
            max_time_exit_rate_pct=self.max_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
        )

    def calibrated_settings(self) -> CalibratedStructureShadowSettings:
        return self.repaired_validation_settings().calibrated_settings()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pct(n: float, d: float) -> float:
    return 0.0 if d <= 0 else n / d * 100.0


def _safe_upper(value: Any) -> str:
    return str(value or "").upper()


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    # pandas-style strings often include a space before timezone.
    try:
        return datetime.fromisoformat(s.replace(" UTC", "+00:00"))
    except Exception:
        return None


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: tuple[int, dict[str, Any]]) -> tuple[str, int]:
        idx, row = item
        dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
        return ((dt.isoformat() if dt else "9999-12-31T23:59:59+00:00"), idx)
    return [row for _, row in sorted(enumerate(rows), key=key)]


def _gate(summary: dict[str, Any], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    candidates = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    win = _safe_float(summary.get("win_rate_pct"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 0.0)
    time_exit = _safe_float(summary.get("time_exit_rate_pct"), 0.0)
    checks = {
        "sample_ok": candidates >= settings.min_variant_candidates,
        "expectancy_ok": expectancy >= settings.min_expectancy_r,
        "win_rate_ok": win >= settings.min_win_rate_pct,
        "loss_rate_ok": loss <= settings.max_loss_rate_pct,
        "time_exit_ok": time_exit <= settings.max_time_exit_rate_pct,
        "min_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
    }
    checks["passes_candidate_gate"] = bool(
        checks["sample_ok"]
        and checks["expectancy_ok"]
        and checks["win_rate_ok"]
        and checks["loss_rate_ok"]
        and checks["time_exit_ok"]
    )
    return checks


def _holdout_gate(summary: dict[str, Any], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    candidates = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    win = _safe_float(summary.get("win_rate_pct"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 0.0)
    checks = {
        "sample_ok": candidates >= settings.min_holdout_candidates,
        "expectancy_ok": expectancy >= settings.min_holdout_expectancy_r,
        "win_rate_ok": win >= settings.min_holdout_win_rate_pct,
        "loss_rate_ok": loss <= settings.max_holdout_loss_rate_pct,
        "min_holdout_candidates": settings.min_holdout_candidates,
        "min_holdout_expectancy_r": settings.min_holdout_expectancy_r,
        "min_holdout_win_rate_pct": settings.min_holdout_win_rate_pct,
        "max_holdout_loss_rate_pct": settings.max_holdout_loss_rate_pct,
    }
    checks["passes_holdout_gate"] = bool(checks["sample_ok"] and checks["expectancy_ok"] and checks["win_rate_ok"] and checks["loss_rate_ok"])
    return checks


def _fold_gate(summary: dict[str, Any], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    candidates = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    win = _safe_float(summary.get("win_rate_pct"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 0.0)
    return {
        "sample_ok": candidates >= settings.min_fold_candidates,
        "expectancy_non_negative": expectancy >= 0.0,
        "win_rate_floor_ok": win >= 50.0,
        "loss_rate_floor_ok": loss <= 55.0,
        "passes_fold_guard": bool(candidates >= settings.min_fold_candidates and expectancy >= 0.0 and win >= 50.0 and loss <= 55.0),
        "min_fold_candidates": settings.min_fold_candidates,
    }


def _summary_with_gate(rows: list[dict[str, Any]], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    summary = _summarize_rows(rows)
    summary["gate_checks"] = _gate(summary, settings)
    return summary


def _target_map_score_65_79(row: dict[str, Any], settings: IndependentRepairedValidationSettings) -> bool:
    score = _safe_float(row.get("map_score"), 0.0)
    return settings.map_score_candidate_min <= score <= settings.map_score_candidate_max


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: IndependentRepairedValidationSettings, description: str) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    return {
        "name": name,
        "description": description,
        **_summary_with_gate(selected, settings),
    }


def _component_quality(rows: list[dict[str, Any]], group_fn: Callable[[dict[str, Any]], str], settings: IndependentRepairedValidationSettings, *, min_candidates: int | None = None) -> list[dict[str, Any]]:
    min_n = settings.min_component_candidates if min_candidates is None else int(min_candidates)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(group_fn(r) or "NA")].append(r)
    out: list[dict[str, Any]] = []
    for key, vals in groups.items():
        if len(vals) < min_n:
            continue
        summary = _summarize_rows(vals)
        summary["component"] = key
        out.append(summary)
    out.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_float(x.get("win_rate_pct"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for i, item in enumerate(out, start=1):
        item["rank"] = i
    return out


def _selector_variants(rows: list[dict[str, Any]], settings: IndependentRepairedValidationSettings) -> list[dict[str, Any]]:
    return sorted([
        _variant("map_score_65_79_all", rows, lambda r: _target_map_score_65_79(r, settings), settings, "29.5.0i best candidate revalidated as aggregate MAP_SCORE_65_79."),
        _variant("map_score_65_79_repaired_entry_state", rows, lambda r: _target_map_score_65_79(r, settings) and _is_entry_state(r), settings, "MAP_SCORE_65_79 with repaired CONTEXT/CONFIRMATION only."),
        _variant("map_score_65_79_repaired_confirmation", rows, lambda r: _target_map_score_65_79(r, settings) and _is_confirmation(r), settings, "MAP_SCORE_65_79 with true repaired CONFIRMATION only."),
        _variant("map_score_65_79_clean", rows, lambda r: _target_map_score_65_79(r, settings) and _is_clean(r), settings, "MAP_SCORE_65_79 with clean pattern/range."),
        _variant("map_score_65_79_no_wait_no_conflict", rows, lambda r: _target_map_score_65_79(r, settings) and not _is_wait(r) and not str(r.get("structure_state") or "").upper().startswith("CONFLICT"), settings, "MAP_SCORE_65_79 excluding WAIT and CONFLICT rows."),
        _variant("bos_directional_repaired", rows, _is_directional_bos, settings, "Directionally matching BOS after repair."),
        _variant("bos_directional_map_score_65_79", rows, lambda r: _target_map_score_65_79(r, settings) and _is_directional_bos(r), settings, "Directionally matching BOS inside MAP_SCORE_65_79."),
        _variant("wait_map_score_65_79_watchlist_only", rows, lambda r: _target_map_score_65_79(r, settings) and _is_wait(r), settings, "WAIT rows inside MAP_SCORE_65_79; diagnostic watchlist only."),
        _variant("no_structure_map_score_65_79_blocked", rows, lambda r: _target_map_score_65_79(r, settings) and _is_no_structure(r), settings, "NO_STRUCTURE rows inside MAP_SCORE_65_79; blocked from entry."),
    ], key=lambda v: (bool((v.get("gate_checks") or {}).get("passes_candidate_gate")), _safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)


def _period_label(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"start": "", "end": ""}
    dts = [_parse_dt(r.get("datetime") or r.get("timestamp") or r.get("time")) for r in rows]
    dts = [d for d in dts if d is not None]
    if not dts:
        return {"start": "", "end": ""}
    return {"start": min(dts).isoformat(), "end": max(dts).isoformat()}


def _walk_forward(rows: list[dict[str, Any]], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    ordered = _sort_rows(rows)
    n = len(ordered)
    if n <= 0:
        return {"folds": [], "holdout": {}, "stability_checks": {"passes_walk_forward_guard": False, "reason": "no_rows"}}
    fold_count = max(2, min(settings.fold_count, n))
    folds: list[dict[str, Any]] = []
    for idx in range(fold_count):
        start = int(round(idx * n / fold_count))
        end = int(round((idx + 1) * n / fold_count))
        vals = ordered[start:end]
        summary = _summarize_rows(vals)
        summary["fold"] = idx + 1
        summary["period"] = _period_label(vals)
        summary["fold_checks"] = _fold_gate(summary, settings)
        folds.append(summary)
    holdout_n = min(n, max(settings.min_holdout_candidates, int(math.ceil(n * settings.holdout_fraction))))
    holdout_rows = ordered[-holdout_n:] if holdout_n > 0 else []
    holdout_summary = _summarize_rows(holdout_rows)
    holdout_summary["period"] = _period_label(holdout_rows)
    holdout_summary["holdout_checks"] = _holdout_gate(holdout_summary, settings)
    valid_folds = [f for f in folds if _safe_int(f.get("candidates"), 0) > 0]
    positive_folds = [f for f in valid_folds if _safe_float(f.get("expectancy_r"), 0.0) > 0.0]
    passing_folds = [f for f in valid_folds if bool((f.get("fold_checks") or {}).get("passes_fold_guard"))]
    positive_fold_rate = _pct(len(positive_folds), len(valid_folds))
    passing_fold_rate = _pct(len(passing_folds), len(valid_folds))
    expectancy_values = [_safe_float(f.get("expectancy_r"), 0.0) for f in valid_folds]
    expectancy_range = (max(expectancy_values) - min(expectancy_values)) if expectancy_values else 0.0
    checks = {
        "fold_count": len(valid_folds),
        "positive_folds": len(positive_folds),
        "positive_fold_rate_pct": round(positive_fold_rate, 4),
        "passing_fold_rate_pct": round(passing_fold_rate, 4),
        "min_positive_fold_rate_pct": settings.min_positive_fold_rate_pct,
        "expectancy_range_r": round(expectancy_range, 6),
        "positive_fold_rate_ok": positive_fold_rate >= settings.min_positive_fold_rate_pct,
        "holdout_ok": bool((holdout_summary.get("holdout_checks") or {}).get("passes_holdout_gate")),
    }
    checks["passes_walk_forward_guard"] = bool(checks["positive_fold_rate_ok"] and checks["holdout_ok"])
    return {"folds": folds, "holdout": holdout_summary, "stability_checks": checks}


def _concentration(rows: list[dict[str, Any]], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    total = len(rows)
    assets = Counter(str(r.get("symbol") or "NA") for r in rows)
    sides = Counter(str(r.get("side") or "NA") for r in rows)
    states = Counter(str(r.get("structure_state") or "NA") for r in rows)
    max_asset = max(assets.values(), default=0)
    max_side = max(sides.values(), default=0)
    checks = {
        "asset_concentration_pct": round(_pct(max_asset, total), 4),
        "side_concentration_pct": round(_pct(max_side, total), 4),
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
        "asset_concentration_ok": _pct(max_asset, total) <= settings.max_asset_concentration_pct if total else False,
        "side_concentration_ok": _pct(max_side, total) <= settings.max_side_concentration_pct if total else False,
        "distinct_assets": len(assets),
        "distinct_sides": len([k for k, v in sides.items() if v > 0]),
    }
    checks["passes_concentration_guard"] = bool(checks["asset_concentration_ok"] and checks["side_concentration_ok"] and checks["distinct_assets"] >= 2)
    return {
        "asset_counts": dict(assets),
        "side_counts": dict(sides),
        "state_counts": dict(states),
        "checks": checks,
    }


def _independent_matrix(target_rows: list[dict[str, Any]], rows: list[dict[str, Any]], settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    return {
        "target_variant": TARGET_VARIANT_NAME,
        "target_rows": len(target_rows),
        "all_repaired_rows": len(rows),
        "target_entry_state_rows": sum(1 for r in target_rows if _is_entry_state(r)),
        "target_confirmation_rows": sum(1 for r in target_rows if _is_confirmation(r)),
        "target_bos_rows": sum(1 for r in target_rows if _is_directional_bos(r)),
        "target_wait_rows": sum(1 for r in target_rows if _is_wait(r)),
        "target_no_structure_rows": sum(1 for r in target_rows if _is_no_structure(r)),
        "target_clean_rows": sum(1 for r in target_rows if _is_clean(r)),
        "map_score_min": settings.map_score_candidate_min,
        "map_score_max": settings.map_score_candidate_max,
    }


def _fallback_from_existing_reports(base: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"available": False}
    for filename in [
        "repaired_structure_shadow_validation_report.json",
        "structure_context_repair_report.json",
        "structure_filter_diagnostics_report.json",
    ]:
        path = base / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            out[filename] = {
                "status": payload.get("status") if isinstance(payload, dict) else "INVALID",
                "decision": ((payload.get("decision") or {}).get("status") if isinstance(payload.get("decision"), dict) else "NA") if isinstance(payload, dict) else "NA",
                "counts": payload.get("counts", {}) if isinstance(payload, dict) else {},
            }
            out["available"] = True
        except Exception as exc:
            out[filename] = {"status": "READ_ERROR", "error": str(exc)}
    return out


def _decision(target_summary: dict[str, Any], walk_forward: dict[str, Any], concentration: dict[str, Any], variants: list[dict[str, Any]], rows: list[dict[str, Any]], fallback: dict[str, Any]) -> dict[str, Any]:
    if not rows and fallback.get("available"):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "Detailed repaired rows unavailable; fallback reports are insufficient for independent walk-forward validation.",
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "fallback_summary_only": True,
            "next_patch": "Rerun 29.5.0j locally with parquet support before paper unlock refinement.",
        }
    target_gate = target_summary.get("gate_checks", {}) if isinstance(target_summary.get("gate_checks"), dict) else {}
    wf_checks = walk_forward.get("stability_checks", {}) if isinstance(walk_forward.get("stability_checks"), dict) else {}
    concentration_checks = concentration.get("checks", {}) if isinstance(concentration.get("checks"), dict) else {}
    guard_pass = bool(
        target_gate.get("passes_candidate_gate")
        and wf_checks.get("passes_walk_forward_guard")
        and concentration_checks.get("passes_concentration_guard")
    )
    if guard_pass:
        return {
            "status": "STABILITY_CANDIDATE_DIAGNOSTIC",
            "reason": "MAP_SCORE_65_79 passed aggregate, walk-forward, holdout and concentration diagnostic guards. Operational unlock remains blocked pending a separate paper-unlock refinement patch.",
            "best_stability_variant": target_summary,
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "paper_unlock_refinement_candidate": True,
            "candidate_profile_status": "NON_OPERATIONAL_STABILITY_CANDIDATE",
            "next_patch": "29.4.4c paper unlock profile refinement design, diagnostic-only and still no live/testnet.",
        }
    reasons: list[str] = []
    if not target_gate.get("passes_candidate_gate"):
        reasons.append("aggregate MAP_SCORE_65_79 candidate gate failed")
    if not wf_checks.get("passes_walk_forward_guard"):
        reasons.append("walk-forward or holdout guard failed")
    if not concentration_checks.get("passes_concentration_guard"):
        reasons.append("asset/side concentration guard failed")
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "; ".join(reasons or ["independent stability validation did not pass"]),
        "best_stability_variant": target_summary if target_summary else (variants[0] if variants else {}),
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_refinement_candidate": False,
        "recommended_actions": [
            "Keep MAP_SCORE_65_79 diagnostic-only until walk-forward/holdout stability passes.",
            "Do not lower thresholds or use the 29.5.0i aggregate candidate as an entry trigger.",
            "Inspect weak folds and recent holdout before any paper unlock profile refinement.",
            "Keep WAIT, NO_STRUCTURE and CONFLICT non-entry even when their local expectancy is positive.",
        ],
        "next_patch": "29.5.0j-1 stability repair / sample expansion or wait for more repaired shadow rows, not paper unlock yet",
    }


def _settings_payload(settings: IndependentRepairedValidationSettings) -> dict[str, Any]:
    return {
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_fold_candidates": settings.min_fold_candidates,
        "min_holdout_candidates": settings.min_holdout_candidates,
        "fold_count": settings.fold_count,
        "holdout_fraction": settings.holdout_fraction,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
        "min_holdout_expectancy_r": settings.min_holdout_expectancy_r,
        "min_holdout_win_rate_pct": settings.min_holdout_win_rate_pct,
        "max_holdout_loss_rate_pct": settings.max_holdout_loss_rate_pct,
        "min_positive_fold_rate_pct": settings.min_positive_fold_rate_pct,
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
    }


def build_independent_repaired_validation_report(data_dir: str | Path = "data", settings: IndependentRepairedValidationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or IndependentRepairedValidationSettings.from_config()
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    fallback = _fallback_from_existing_reports(base) if not rows else {"available": False}
    target_rows = [r for r in rows if _target_map_score_65_79(r, settings)]
    target_summary = _summary_with_gate(target_rows, settings)
    target_summary["name"] = TARGET_VARIANT_NAME
    target_summary["description"] = "Independent 29.5.0j revalidation of 29.5.0i MAP_SCORE_65_79 aggregate candidate."
    variants = _selector_variants(rows, settings) if rows else []
    walk_forward = _walk_forward(target_rows, settings) if target_rows else {"folds": [], "holdout": {}, "stability_checks": {"passes_walk_forward_guard": False, "reason": "no_target_rows"}}
    concentration = _concentration(target_rows, settings) if target_rows else {"asset_counts": {}, "side_counts": {}, "state_counts": {}, "checks": {"passes_concentration_guard": False}}
    matrix = _independent_matrix(target_rows, rows, settings) if rows else {}
    component_audit = {
        "target_by_asset_side": _component_quality(target_rows, lambda r: f"{r.get('symbol') or 'NA'}:{r.get('side') or 'NA'}", settings, min_candidates=3),
        "target_by_state": _component_quality(target_rows, lambda r: str(r.get("structure_state") or "NA"), settings, min_candidates=3),
        "target_by_confirmation_summary": _component_quality(target_rows, lambda r: str(r.get("confirmation_summary") or "NA"), settings, min_candidates=3),
        "target_by_price_location": _component_quality(target_rows, lambda r: str(r.get("price_location") or "NA"), settings, min_candidates=3),
        "target_by_structure_bias": _component_quality(target_rows, lambda r: str(r.get("structure_bias") or "NA"), settings, min_candidates=3),
    } if target_rows else {}
    decision = _decision(target_summary, walk_forward, concentration, variants, rows, fallback)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "STABILITY_CANDIDATE_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "independent_repaired_validation_stability_guard",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "safety": {
            "no_orders": True,
            "no_live": True,
            "no_testnet": True,
            "paper_unlock_unchanged": True,
            "risk_unchanged": True,
            "diagnostic_only": True,
        },
        "counts": {
            "scenario_pattern_evaluation_rows": historical.get("scenario_pattern_evaluation_rows", 0),
            "candidate_rows_pre_structure": historical.get("candidate_rows_pre_structure", 0),
            "structured_candidate_rows": len(rows),
            "target_candidate_rows": len(target_rows),
            "validation_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "target_candidate": target_summary,
        "walk_forward": walk_forward,
        "concentration": concentration,
        "independent_matrix": matrix,
        "validation_variants": variants,
        "validation_variants_top": variants[:12],
        "component_audit": component_audit,
        "historical_summary": _summarize_rows(rows),
        "by_asset": historical.get("by_asset", {}),
        "fallback": fallback,
        "warnings": historical.get("warnings", []),
        "recent_target_rows": [
            {
                "symbol": r.get("symbol"),
                "datetime": r.get("datetime"),
                "side": r.get("side"),
                "bucket": r.get("bucket"),
                "pattern_score": r.get("pattern_score"),
                "range_pos_400": r.get("range_pos_400"),
                "map_score": r.get("map_score"),
                "structure_bias": r.get("structure_bias"),
                "price_location": r.get("price_location"),
                "confirmation_summary": r.get("confirmation_summary"),
                "structure_state": r.get("structure_state"),
                "structure_relabel": r.get("structure_relabel"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in _sort_rows(target_rows)[-20:]
        ],
        "files": {
            "report": str(base / REPORT_NAME),
            "repaired_structure_shadow_validation": str(base / "repaired_structure_shadow_validation_report.json"),
            "structure_context_repair": str(base / "structure_context_repair_report.json"),
            "structure_filter_diagnostics": str(base / "structure_filter_diagnostics_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_independent_repaired_validation_report(data_dir: str | Path = "data", settings: IndependentRepairedValidationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_independent_repaired_validation_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "IndependentRepairedValidationSettings",
    "build_independent_repaired_validation_report",
    "write_independent_repaired_validation_report",
]
