"""Prompt 29.5.0i repaired structure shadow validation / component audit.

Diagnostic-only validation layer after 29.5.0h.

The 29.5.0h repair showed that legacy structure context had to be split into
CONTEXT / WAIT / CONFIRMATION / CONFLICT / NO_STRUCTURE, but no entry-quality
variant passed diagnostic gates.  This module validates the repaired rows with a
focused shadow audit of the only hypotheses that still looked worth studying:

- MAP_SCORE_65_79 after repaired context rules;
- directionally matching BOS after repair;
- WAIT states as watchlist-only, never as entry confirmation;
- NO_STRUCTURE positive anomaly, explicitly non-entry;
- repaired CONFIRMATION quality by side, asset and component.

Safety invariant: no orders, no live, no testnet, no threshold/risk/unlock
mutation.  The output is ``repaired_structure_shadow_validation_report.json``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
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
from core.structure_context_repair import (
    STATE_CONFIRMATION,
    STATE_CONFLICT,
    STATE_CONTEXT,
    STATE_NO_STRUCTURE,
    STATE_WAIT,
    StructureContextRepairSettings,
    repair_structure_rows,
)

REPORT_NAME = "repaired_structure_shadow_validation_report.json"
PROMPT_ID = "29.5.0i"
NON_ENTRY_VARIANTS = {
    "wait_states_watchlist_only",
    "no_structure_anomaly_watchlist_only",
    "conflict_rows_blocked",
}


@dataclass(frozen=True)
class RepairedStructureShadowValidationSettings:
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
    min_expectancy_r: float = 0.10
    min_win_rate_pct: float = 52.0
    max_loss_rate_pct: float = 45.0
    max_time_exit_rate_pct: float = 60.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    score_thresholds: tuple[float, ...] = (60.0, 65.0, 70.0)

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "RepairedStructureShadowValidationSettings":
        return cls(
            enabled=bool(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_ROWS_PER_ASSET", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_EVAL_STRIDE", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_STRUCTURE_WINDOW_ROWS", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_VARIANT_CANDIDATES", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_component_candidates=max(3, _safe_int(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_COMPONENT_CANDIDATES", 10), 10)),
            min_expectancy_r=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_EXPECTANCY_R", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MIN_WIN_RATE_PCT", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_LOSS_RATE_PCT", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            score_thresholds=_parse_float_tuple(getattr(cfg, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_SCORE_THRESHOLDS", getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_SCORE_THRESHOLDS", "60,65,70")), (60.0, 65.0, 70.0)),
        )

    def repair_settings(self) -> StructureContextRepairSettings:
        return StructureContextRepairSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            min_expectancy_r=self.min_expectancy_r,
            min_win_rate_pct=self.min_win_rate_pct,
            max_loss_rate_pct=self.max_loss_rate_pct,
            max_time_exit_rate_pct=self.max_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
            score_thresholds=self.score_thresholds,
        )

    def calibrated_settings(self) -> CalibratedStructureShadowSettings:
        return self.repair_settings().calibrated_settings()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_float_tuple(value: Any, default: tuple[float, ...]) -> tuple[float, ...]:
    try:
        vals = [_safe_float(str(x).strip(), float("nan")) for x in str(value).replace(";", ",").split(",") if str(x).strip()]
        out = tuple(sorted({float(x) for x in vals if math.isfinite(float(x))}))
        return out or default
    except Exception:
        return default


def _pct(n: float, d: float) -> float:
    return 0.0 if d <= 0 else n / d * 100.0


def _gate(summary: dict[str, Any], settings: RepairedStructureShadowValidationSettings, *, require_entry: bool = True) -> dict[str, Any]:
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
        "entry_candidate_allowed": bool(require_entry),
        "min_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
    }
    checks["passes_candidate_gate"] = bool(
        checks["entry_candidate_allowed"]
        and checks["sample_ok"]
        and checks["expectancy_ok"]
        and checks["win_rate_ok"]
        and checks["loss_rate_ok"]
        and checks["time_exit_ok"]
    )
    return checks


def _safe_upper(value: Any) -> str:
    return str(value or "").upper()


def _is_clean(row: dict[str, Any]) -> bool:
    return (not row.get("has_conflicting_patterns")) and bool(row.get("range_filter_ok"))


def _is_focus(row: dict[str, Any], settings: RepairedStructureShadowValidationSettings) -> bool:
    return _safe_upper(row.get("symbol")) == settings.focus_symbol and _safe_upper(row.get("bucket")) == settings.focus_bucket


def _state(row: dict[str, Any]) -> str:
    return str(row.get("structure_state") or STATE_NO_STRUCTURE)


def _is_entry_state(row: dict[str, Any]) -> bool:
    return _state(row) in {STATE_CONTEXT, STATE_CONFIRMATION} and bool(row.get("repaired_structure_context_ok"))


def _is_confirmation(row: dict[str, Any]) -> bool:
    return _state(row) == STATE_CONFIRMATION and bool(row.get("repaired_structure_confirmed"))


def _is_wait(row: dict[str, Any]) -> bool:
    return _state(row) == STATE_WAIT or bool(row.get("repaired_wait_state"))


def _is_no_structure(row: dict[str, Any]) -> bool:
    return _state(row) == STATE_NO_STRUCTURE or bool(row.get("repaired_no_structure"))


def _is_conflict(row: dict[str, Any]) -> bool:
    return _state(row) == STATE_CONFLICT or bool(row.get("repaired_conflict"))


def _in_map_score_65_79(row: dict[str, Any], settings: RepairedStructureShadowValidationSettings) -> bool:
    score = _safe_float(row.get("map_score"), 0.0)
    return settings.map_score_candidate_min <= score <= settings.map_score_candidate_max


def _is_directional_bos(row: dict[str, Any]) -> bool:
    side = _safe_upper(row.get("side"))
    if _is_conflict(row):
        return False
    if side == "BUY":
        return bool(row.get("bos_bullish"))
    if side == "SELL":
        return bool(row.get("bos_bearish"))
    return False


def _is_directional_choch(row: dict[str, Any]) -> bool:
    side = _safe_upper(row.get("side"))
    if _is_conflict(row):
        return False
    if side == "BUY":
        return bool(row.get("choch_bullish"))
    if side == "SELL":
        return bool(row.get("choch_bearish"))
    return False


def _is_directional_mss(row: dict[str, Any]) -> bool:
    side = _safe_upper(row.get("side"))
    if _is_conflict(row):
        return False
    if side == "BUY":
        return bool(row.get("mss_bullish"))
    if side == "SELL":
        return bool(row.get("mss_bearish"))
    return False


def _variant(
    name: str,
    rows: list[dict[str, Any]],
    fn: Callable[[dict[str, Any]], bool],
    settings: RepairedStructureShadowValidationSettings,
    description: str,
    *,
    entry_candidate: bool = True,
) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    summary = _summarize_rows(selected)
    gate = _gate(summary, settings, require_entry=entry_candidate)
    return {
        "name": name,
        "description": description,
        "entry_candidate": bool(entry_candidate),
        "gate_checks": gate,
        "passes_candidate_gate": bool(gate.get("passes_candidate_gate")),
        **summary,
    }


def _side_asset_breakdown(rows: list[dict[str, Any]], settings: RepairedStructureShadowValidationSettings, *, min_candidates: int | None = None) -> list[dict[str, Any]]:
    min_n = settings.min_component_candidates if min_candidates is None else int(min_candidates)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = f"{r.get('symbol') or 'NA'}:{r.get('side') or 'NA'}:{r.get('structure_state') or 'NA'}"
        groups[key].append(r)
    out: list[dict[str, Any]] = []
    for key, vals in groups.items():
        if len(vals) < min_n:
            continue
        summary = _summarize_rows(vals)
        summary["component"] = key
        out.append(summary)
    out.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_float(x.get("win_rate_pct"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for idx, item in enumerate(out, start=1):
        item["rank"] = idx
    return out


def _component_quality(
    rows: list[dict[str, Any]],
    group_fn: Callable[[dict[str, Any]], str],
    settings: RepairedStructureShadowValidationSettings,
    *,
    min_candidates: int | None = None,
) -> list[dict[str, Any]]:
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
    for idx, item in enumerate(out, start=1):
        item["rank"] = idx
    return out


def _map_score_bucket(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("map_score"), 0.0)
    if score < 35:
        return "MAP_SCORE_UNDER_35"
    if score < 50:
        return "MAP_SCORE_35_49"
    if score < 65:
        return "MAP_SCORE_50_64"
    if score < 80:
        return "MAP_SCORE_65_79"
    return "MAP_SCORE_80_PLUS"


def _bos_family(row: dict[str, Any]) -> str:
    side = _safe_upper(row.get("side"))
    if side == "BUY" and row.get("bos_bullish"):
        return "BOS_DIRECTIONAL_BUY"
    if side == "SELL" and row.get("bos_bearish"):
        return "BOS_DIRECTIONAL_SELL"
    if row.get("bos_bullish") or row.get("bos_bearish"):
        return "BOS_OPPOSITE_OR_MIXED"
    return "NO_BOS"


def _validation_hypotheses(rows: list[dict[str, Any]], settings: RepairedStructureShadowValidationSettings) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = [
        _variant("all_repaired_rows", rows, lambda r: True, settings, "All structured rows after 29.5.0h repair.", entry_candidate=False),
        _variant("entry_state_context_or_confirmation", rows, _is_entry_state, settings, "Only repaired CONTEXT or CONFIRMATION rows."),
        _variant("repaired_confirmation_only", rows, _is_confirmation, settings, "True repaired directionally matching hard confirmations only."),
        _variant("clean_pattern_range_repaired_entry_state", rows, lambda r: _is_clean(r) and _is_entry_state(r), settings, "Clean pattern/range rows with repaired CONTEXT or CONFIRMATION."),
        _variant("clean_pattern_range_repaired_confirmation", rows, lambda r: _is_clean(r) and _is_confirmation(r), settings, "Clean pattern/range rows with repaired CONFIRMATION only."),
        _variant("map_score_65_79_all", rows, lambda r: _in_map_score_65_79(r, settings), settings, "MAP_SCORE_65_79 hypothesis without using it as an entry trigger."),
        _variant("map_score_65_79_repaired_entry_state", rows, lambda r: _in_map_score_65_79(r, settings) and _is_entry_state(r), settings, "MAP_SCORE_65_79 plus repaired CONTEXT/CONFIRMATION."),
        _variant("map_score_65_79_repaired_confirmation", rows, lambda r: _in_map_score_65_79(r, settings) and _is_confirmation(r), settings, "MAP_SCORE_65_79 plus true repaired CONFIRMATION."),
        _variant("map_score_65_79_clean_repaired_entry_state", rows, lambda r: _in_map_score_65_79(r, settings) and _is_clean(r) and _is_entry_state(r), settings, "MAP_SCORE_65_79 with clean pattern/range and repaired CONTEXT/CONFIRMATION."),
        _variant("bos_directional_repaired", rows, _is_directional_bos, settings, "Directionally matching BOS after repair."),
        _variant("bos_directional_clean_repaired", rows, lambda r: _is_clean(r) and _is_directional_bos(r), settings, "Directionally matching BOS with clean pattern/range after repair."),
        _variant("choch_directional_repaired", rows, _is_directional_choch, settings, "Directionally matching CHOCH after repair."),
        _variant("mss_directional_repaired", rows, _is_directional_mss, settings, "Directionally matching MSS after repair."),
        _variant("wait_states_watchlist_only", rows, _is_wait, settings, "WAIT states kept watchlist-only; never entry confirmation.", entry_candidate=False),
        _variant("wait_states_clean_watchlist_only", rows, lambda r: _is_clean(r) and _is_wait(r), settings, "Clean WAIT states kept watchlist-only; never entry confirmation.", entry_candidate=False),
        _variant("no_structure_anomaly_watchlist_only", rows, _is_no_structure, settings, "NO_STRUCTURE positive anomaly audit; non-entry.", entry_candidate=False),
        _variant("conflict_rows_blocked", rows, _is_conflict, settings, "CONFLICT rows are blocked from entry.", entry_candidate=False),
        _variant("btc_focus_clean_repaired_entry_state", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and _is_entry_state(r), settings, "BTC focus clean profile with repaired CONTEXT/CONFIRMATION."),
        _variant("btc_focus_clean_repaired_confirmation", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and _is_confirmation(r), settings, "BTC focus clean profile with repaired CONFIRMATION."),
        _variant("btc_focus_map_score_65_79_clean_repaired_entry", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and _in_map_score_65_79(r, settings) and _is_entry_state(r), settings, "BTC focus clean MAP_SCORE_65_79 repaired entry-state subset."),
        _variant("btc_focus_bos_clean_repaired", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and _is_directional_bos(r), settings, "BTC focus clean directionally matching BOS subset."),
    ]
    for threshold in settings.score_thresholds:
        t = float(threshold)
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_clean_repaired_entry_state",
            rows,
            lambda r, t=t: _is_focus(r, settings) and _is_clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and _is_entry_state(r),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and repaired CONTEXT/CONFIRMATION.",
        ))
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_clean_repaired_confirmation",
            rows,
            lambda r, t=t: _is_focus(r, settings) and _is_clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and _is_confirmation(r),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and repaired CONFIRMATION.",
        ))
    variants.sort(key=lambda v: (bool(v.get("passes_candidate_gate")), bool(v.get("entry_candidate")), _safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)
    for idx, v in enumerate(variants, start=1):
        v["rank"] = idx
    return variants


def _component_audit(rows: list[dict[str, Any]], settings: RepairedStructureShadowValidationSettings) -> dict[str, Any]:
    entry_rows = [r for r in rows if _is_entry_state(r)]
    confirmation_rows = [r for r in rows if _is_confirmation(r)]
    map_65_79 = [r for r in rows if _in_map_score_65_79(r, settings)]
    bos_rows = [r for r in rows if _is_directional_bos(r)]
    wait_rows = [r for r in rows if _is_wait(r)]
    no_structure_rows = [r for r in rows if _is_no_structure(r)]
    return {
        "state_quality": _component_quality(rows, lambda r: _state(r), settings, min_candidates=5),
        "entry_state_by_asset_side": _side_asset_breakdown(entry_rows, settings, min_candidates=3),
        "confirmation_by_asset_side": _side_asset_breakdown(confirmation_rows, settings, min_candidates=3),
        "map_score_bucket_quality": _component_quality(rows, _map_score_bucket, settings, min_candidates=10),
        "map_score_65_79_by_asset_side_state": _side_asset_breakdown(map_65_79, settings, min_candidates=3),
        "bos_family_quality": _component_quality(rows, _bos_family, settings, min_candidates=5),
        "directional_bos_by_asset_side": _side_asset_breakdown(bos_rows, settings, min_candidates=2),
        "wait_by_summary_side": _component_quality(wait_rows, lambda r: f"{r.get('side') or 'NA'}:{r.get('confirmation_summary') or 'NA'}", settings, min_candidates=2),
        "no_structure_by_asset_side": _side_asset_breakdown(no_structure_rows, settings, min_candidates=3),
        "confirmation_summary_quality": _component_quality(entry_rows, lambda r: str(r.get("confirmation_summary") or "NA"), settings, min_candidates=3),
        "price_location_quality": _component_quality(entry_rows, lambda r: str(r.get("price_location") or "NA"), settings, min_candidates=3),
    }


def _hypothesis_matrix(rows: list[dict[str, Any]], settings: RepairedStructureShadowValidationSettings) -> dict[str, Any]:
    total = len(rows)
    states = Counter(_state(r) for r in rows)
    map_rows = [r for r in rows if _in_map_score_65_79(r, settings)]
    bos_rows = [r for r in rows if _is_directional_bos(r)]
    wait_rows = [r for r in rows if _is_wait(r)]
    no_structure_rows = [r for r in rows if _is_no_structure(r)]
    confirmation_rows = [r for r in rows if _is_confirmation(r)]
    return {
        "total_rows": total,
        "state_counts": dict(states),
        "state_rate_pct": {k: round(_pct(v, total), 4) for k, v in states.items()},
        "map_score_65_79_count": len(map_rows),
        "map_score_65_79_rate_pct": round(_pct(len(map_rows), total), 4),
        "map_score_65_79_entry_state_count": sum(1 for r in map_rows if _is_entry_state(r)),
        "map_score_65_79_confirmation_count": sum(1 for r in map_rows if _is_confirmation(r)),
        "directional_bos_count": len(bos_rows),
        "directional_bos_rate_pct": round(_pct(len(bos_rows), total), 4),
        "wait_watchlist_count": len(wait_rows),
        "no_structure_count": len(no_structure_rows),
        "confirmation_count": len(confirmation_rows),
        "conflict_count": sum(1 for r in rows if _is_conflict(r)),
        "clean_entry_state_count": sum(1 for r in rows if _is_clean(r) and _is_entry_state(r)),
        "btc_focus_clean_entry_state_count": sum(1 for r in rows if _is_focus(r, settings) and _is_clean(r) and _is_entry_state(r)),
        "btc_focus_clean_confirmation_count": sum(1 for r in rows if _is_focus(r, settings) and _is_clean(r) and _is_confirmation(r)),
    }


def _fallback_from_existing_reports(base: Path) -> dict[str, Any]:
    paths = {
        "structure_context_repair": base / "structure_context_repair_report.json",
        "structure_filter_diagnostics": base / "structure_filter_diagnostics_report.json",
        "calibrated_structure_shadow": base / "calibrated_structure_shadow_report.json",
        "market_structure_map": base / "market_structure_map_report.json",
    }
    out: dict[str, Any] = {"available": False}
    for name, path in paths.items():
        if not path.exists():
            out[name] = {"status": "MISSING"}
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            out[name] = payload if isinstance(payload, dict) else {"status": "INVALID"}
            out["available"] = True
        except Exception as exc:
            out[name] = {"status": "READ_ERROR", "error": str(exc)}
    return out


def _settings_payload(settings: RepairedStructureShadowValidationSettings) -> dict[str, Any]:
    return {
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_component_candidates": settings.min_component_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "score_thresholds": list(settings.score_thresholds),
    }


def _decision(rows: list[dict[str, Any]], variants: list[dict[str, Any]], matrix: dict[str, Any], fallback: dict[str, Any], settings: RepairedStructureShadowValidationSettings) -> dict[str, Any]:
    if not rows and fallback.get("available"):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "Detailed repaired rows unavailable; fallback reports cannot validate MAP_SCORE_65_79/BOS hypotheses.",
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "fallback_summary_only": True,
            "next_patch": "Rerun 29.5.0i locally with parquet support before any paper unlock refinement.",
        }
    passing = [v for v in variants if bool(v.get("passes_candidate_gate"))]
    passing_entry = [v for v in passing if bool(v.get("entry_candidate")) and v.get("name") not in NON_ENTRY_VARIANTS]
    best = variants[0] if variants else {}
    reasons: list[str] = []
    confirmation_count = _safe_int(matrix.get("confirmation_count"), 0)
    map_count = _safe_int(matrix.get("map_score_65_79_entry_state_count"), 0)
    bos_count = _safe_int(matrix.get("directional_bos_count"), 0)
    if confirmation_count < settings.min_variant_candidates:
        reasons.append("repaired confirmations remain below minimum sample")
    if map_count < settings.min_variant_candidates:
        reasons.append("MAP_SCORE_65_79 repaired entry-state subset remains below minimum sample")
    if bos_count < settings.min_variant_candidates:
        reasons.append("directional BOS subset remains below minimum sample")
    if not passing_entry:
        reasons.append("no repaired entry-quality validation variant passed sample/expectancy/win/loss gates")
    if passing_entry:
        return {
            "status": "VALIDATION_CANDIDATE_DIAGNOSTIC",
            "reason": "At least one repaired validation entry variant passed diagnostic gates, but operational unlock remains blocked pending independent shadow/walk-forward review.",
            "best_validation_variant": passing_entry[0],
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "candidate_profile_status": "NON_OPERATIONAL_DIAGNOSTIC_ONLY",
            "next_patch": "29.5.0j independent repaired validation stability / walk-forward guard before paper unlock refinement",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "; ".join(reasons or ["repaired validation did not establish an unlockable edge"]),
        "best_validation_variant": best,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "recommended_filter_actions": [
            "Keep WAIT and NO_STRUCTURE as watchlist/diagnostic-only, even if their sampled expectancy is positive.",
            "Do not use MAP_SCORE_65_79 as an entry gate until sample size, side/asset stability and loss-rate gates pass after repair.",
            "Do not use BOS as an entry gate until directionally repaired BOS reaches sufficient sample and passes gates.",
            "Keep repaired_structure_context_ok as diagnostic context only; true entry validation must pass independent gates.",
            "Continue collecting repaired CONFIRMATION rows before paper unlock refinement.",
        ],
        "next_patch": "29.5.0j repaired component stability / walk-forward sample expansion, not paper unlock refinement yet",
    }


def build_repaired_structure_shadow_validation_report(data_dir: str | Path = "data", settings: RepairedStructureShadowValidationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or RepairedStructureShadowValidationSettings.from_config()
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    fallback = _fallback_from_existing_reports(base) if not rows else {"available": False}
    variants = _validation_hypotheses(rows, settings) if rows else []
    matrix = _hypothesis_matrix(rows, settings) if rows else {}
    component_audit = _component_audit(rows, settings) if rows else {}
    decision = _decision(rows, variants, matrix, fallback, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "VALIDATION_CANDIDATE_DIAGNOSTIC" else "WARN")

    report = {
        "report_type": "repaired_structure_shadow_validation_component_audit",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
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
            "validation_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "hypotheses": {
            "MAP_SCORE_65_79": "Validate post-repair map-score 65-79 subset by asset/side/state before any operational use.",
            "BOS": "Validate directionally matching BOS after conflict repair as a separate component.",
            "WAIT": "WAIT states remain watchlist-only and cannot be entry confirmations.",
            "NO_STRUCTURE": "NO_STRUCTURE positive anomaly is diagnostic-only and cannot be an entry gate.",
            "CONFIRMATION": "Only repaired CONFIRMATION may be considered entry-quality after passing sample/expectancy/win/loss gates.",
        },
        "historical_summary": _summarize_rows(rows),
        "hypothesis_matrix": matrix,
        "validation_variants": variants,
        "validation_variants_top": variants[:14],
        "component_audit": component_audit,
        "by_asset": historical.get("by_asset", {}),
        "fallback": fallback,
        "warnings": historical.get("warnings", []),
        "recent_rows": [
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
                "repaired_structure_context_ok": r.get("repaired_structure_context_ok"),
                "repaired_structure_confirmed": r.get("repaired_structure_confirmed"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in rows[-20:]
        ],
        "files": {
            "report": str(base / REPORT_NAME),
            "structure_context_repair": str(base / "structure_context_repair_report.json"),
            "structure_filter_diagnostics": str(base / "structure_filter_diagnostics_report.json"),
            "calibrated_structure_shadow": str(base / "calibrated_structure_shadow_report.json"),
            "market_structure_map": str(base / "market_structure_map_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_repaired_structure_shadow_validation_report(data_dir: str | Path = "data", settings: RepairedStructureShadowValidationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_repaired_structure_shadow_validation_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "RepairedStructureShadowValidationSettings",
    "build_repaired_structure_shadow_validation_report",
    "write_repaired_structure_shadow_validation_report",
]
