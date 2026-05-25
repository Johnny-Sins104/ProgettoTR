"""Prompt 29.5.0h strict structure context repair / confirmation relabeling.

Diagnostic-only repair layer after 29.5.0g.

The 29.5.0g audit showed that legacy ``structure_context_ok`` admitted too
many directional conflicts and blurred the line between context, wait states and
true confirmations.  This module repairs that semantic layer by relabeling every
scenario+pattern+structure candidate into one of five mutually exclusive states:

- ``CONFIRMATION``: directionally matching BOS/CHOCH/MSS/retest with confirmation
  close and no unmitigated directional conflict;
- ``CONTEXT``: directional, non-conflicting contextual support/resistance;
- ``WAIT``: liquidity / demand / supply wait state that is not an entry
  confirmation;
- ``CONFLICT``: directional zone conflict, bias conflict, opposite hard
  confirmation or failed retest;
- ``NO_STRUCTURE``: no usable structure.

Safety invariant: no orders, no live, no testnet, no threshold/risk/unlock
mutation.  The output is ``structure_context_repair_report.json``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
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

REPORT_NAME = "structure_context_repair_report.json"
PROMPT_ID = "29.5.0h"
STATE_CONFIRMATION = "CONFIRMATION"
STATE_CONTEXT = "CONTEXT"
STATE_WAIT = "WAIT"
STATE_CONFLICT = "CONFLICT"
STATE_NO_STRUCTURE = "NO_STRUCTURE"


@dataclass(frozen=True)
class StructureContextRepairSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_variant_candidates: int = 50
    min_expectancy_r: float = 0.10
    min_win_rate_pct: float = 52.0
    max_loss_rate_pct: float = 45.0
    max_time_exit_rate_pct: float = 60.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    score_thresholds: tuple[float, ...] = (60.0, 65.0, 70.0)

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "StructureContextRepairSettings":
        return cls(
            enabled=bool(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_ROWS_PER_ASSET", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_EVAL_STRIDE", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_STRUCTURE_WINDOW_ROWS", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_VARIANT_CANDIDATES", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_expectancy_r=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_EXPECTANCY_R", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MIN_WIN_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_LOSS_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MIN", 65.0), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_MAP_SCORE_CANDIDATE_MAX", 79.999), 79.999),
            score_thresholds=_parse_float_tuple(getattr(cfg, "STRUCTURE_CONTEXT_REPAIR_SCORE_THRESHOLDS", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_SCORE_THRESHOLDS", "60,65,70")), (60.0, 65.0, 70.0)),
        )

    def calibrated_settings(self) -> CalibratedStructureShadowSettings:
        base = CalibratedStructureShadowSettings.from_config()
        return CalibratedStructureShadowSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            symbols=base.symbols,
            timeframe=base.timeframe,
            max_rows_per_asset=self.max_rows_per_asset,
            min_warmup_rows=base.min_warmup_rows,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            score_thresholds=tuple(sorted(set(self.score_thresholds + base.score_thresholds))),
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            candidate_profile_name=base.candidate_profile_name,
            support_range_pos_max=base.support_range_pos_max,
            resistance_range_pos_min=base.resistance_range_pos_min,
            min_variant_candidates=self.min_variant_candidates,
            min_structure_expectancy_r=self.min_expectancy_r,
            min_structure_win_rate_pct=self.min_win_rate_pct,
            max_structure_loss_rate_pct=self.max_loss_rate_pct,
            max_confirmed_time_exit_rate_pct=self.max_time_exit_rate_pct,
        )


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


def _metrics(values: Iterable[float]) -> dict[str, float]:
    vals = sorted([_safe_float(v, float("nan")) for v in values])
    vals = [v for v in vals if math.isfinite(v)]
    if not vals:
        return {"count": 0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(q: float) -> float:
        if len(vals) == 1:
            return vals[0]
        idx = int(round((len(vals) - 1) * q))
        return vals[max(0, min(len(vals) - 1, idx))]

    return {
        "count": len(vals),
        "min": round(vals[0], 8),
        "p25": round(pick(0.25), 8),
        "median": round(pick(0.50), 8),
        "p75": round(pick(0.75), 8),
        "max": round(vals[-1], 8),
        "avg": round(float(mean(vals)), 8),
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _directional_flags(row: dict[str, Any]) -> dict[str, Any]:
    side = str(row.get("side") or "").upper()
    bias = str(row.get("structure_bias") or "").upper()
    loc = str(row.get("price_location") or "").upper()
    summary = str(row.get("confirmation_summary") or "").upper()
    nearest = row.get("nearest_liquidity") if isinstance(row.get("nearest_liquidity"), dict) else {}
    nearest_side = str(nearest.get("side") or "").upper()
    nearest_dist = _safe_float(nearest.get("distance_pct"), 999.0)

    in_demand = _as_bool(row.get("in_demand_zone")) or "DEMAND" in loc
    in_supply = _as_bool(row.get("in_supply_zone")) or "SUPPLY" in loc
    lower_context = "LOW" in loc or in_demand
    upper_context = "HIGH" in loc or in_supply
    near_below = _as_bool(row.get("liquidity_below_lows")) or (nearest_side == "BELOW" and nearest_dist <= 0.50)
    near_above = _as_bool(row.get("liquidity_above_highs")) or (nearest_side == "ABOVE" and nearest_dist <= 0.50)
    confirmation_close = _as_bool(row.get("confirmation_close"))

    bullish_break = _as_bool(row.get("bos_bullish")) or _as_bool(row.get("choch_bullish")) or _as_bool(row.get("mss_bullish")) or _as_bool(row.get("breakout_retest_confirmed"))
    bearish_break = _as_bool(row.get("bos_bearish")) or _as_bool(row.get("choch_bearish")) or _as_bool(row.get("mss_bearish")) or _as_bool(row.get("breakdown_retest_confirmed"))
    bullish_hard = bool(confirmation_close and bullish_break)
    bearish_hard = bool(confirmation_close and bearish_break)

    raw_buy_supply = side == "BUY" and in_supply
    raw_sell_demand = side == "SELL" and in_demand
    unmitigated_buy_supply = bool(raw_buy_supply and not bullish_hard)
    unmitigated_sell_demand = bool(raw_sell_demand and not bearish_hard)
    bias_conflict = bool((side == "BUY" and bias.startswith("BEARISH") and not bullish_hard) or (side == "SELL" and bias.startswith("BULLISH") and not bearish_hard))
    opposite_hard = bool((side == "BUY" and bearish_hard) or (side == "SELL" and bullish_hard))
    failed_retest = _as_bool(row.get("failed_retest"))
    wait_state = bool("WAIT" in summary or "NEAR_LIQUIDITY" in summary)
    no_structural = bool("NO_STRUCTURAL" in summary or summary in {"", "NA", "NONE", "UNKNOWN"})

    if side == "BUY":
        directional_context = bool(
            bias.startswith("BULLISH")
            or in_demand
            or lower_context
            or near_below
            or bullish_break
            or "BULLISH" in summary
            or "DEMAND" in summary
        )
        hard_confirmation = bullish_hard
    elif side == "SELL":
        directional_context = bool(
            bias.startswith("BEARISH")
            or in_supply
            or upper_context
            or near_above
            or bearish_break
            or "BEARISH" in summary
            or "SUPPLY" in summary
        )
        hard_confirmation = bearish_hard
    else:
        directional_context = False
        hard_confirmation = False

    conflict_reasons: list[str] = []
    if unmitigated_buy_supply:
        conflict_reasons.append("BUY_IN_SUPPLY_WITHOUT_BULLISH_CONFIRMATION")
    if unmitigated_sell_demand:
        conflict_reasons.append("SELL_IN_DEMAND_WITHOUT_BEARISH_CONFIRMATION")
    if bias_conflict:
        conflict_reasons.append("STRUCTURE_BIAS_CONFLICT")
    if opposite_hard:
        conflict_reasons.append("OPPOSITE_HARD_CONFIRMATION")
    if failed_retest:
        conflict_reasons.append("FAILED_RETEST")

    return {
        "side": side,
        "bias": bias,
        "price_location": loc,
        "summary": summary,
        "in_demand": in_demand,
        "in_supply": in_supply,
        "lower_context": lower_context,
        "upper_context": upper_context,
        "near_below": near_below,
        "near_above": near_above,
        "confirmation_close": confirmation_close,
        "bullish_break": bullish_break,
        "bearish_break": bearish_break,
        "bullish_hard": bullish_hard,
        "bearish_hard": bearish_hard,
        "hard_confirmation": hard_confirmation,
        "directional_context": directional_context,
        "wait_state": wait_state,
        "no_structural": no_structural,
        "raw_buy_supply": raw_buy_supply,
        "raw_sell_demand": raw_sell_demand,
        "unmitigated_buy_supply": unmitigated_buy_supply,
        "unmitigated_sell_demand": unmitigated_sell_demand,
        "bias_conflict": bias_conflict,
        "opposite_hard": opposite_hard,
        "failed_retest": failed_retest,
        "conflict_reasons": conflict_reasons,
    }


def classify_structure_state(row: dict[str, Any]) -> dict[str, Any]:
    flags = _directional_flags(row)
    summary = flags["summary"]
    state = STATE_NO_STRUCTURE
    reasons = list(flags["conflict_reasons"])

    if reasons:
        state = STATE_CONFLICT
    elif flags["hard_confirmation"]:
        state = STATE_CONFIRMATION
        reasons.append("DIRECTIONAL_HARD_CONFIRMATION")
    elif flags["wait_state"]:
        state = STATE_WAIT
        reasons.append("WAIT_STATE_NOT_ENTRY_CONFIRMATION")
    elif flags["no_structural"]:
        state = STATE_NO_STRUCTURE
        reasons.append("NO_USABLE_STRUCTURE")
    elif flags["directional_context"]:
        state = STATE_CONTEXT
        reasons.append("DIRECTIONAL_CONTEXT_ONLY")
    else:
        state = STATE_NO_STRUCTURE
        reasons.append("NO_DIRECTIONAL_CONTEXT")

    side = flags["side"] or "NA"
    relabel = f"{state}:{side}:{summary or 'NA'}"
    return {
        "structure_state": state,
        "structure_relabel": relabel,
        "structure_repair_reasons": reasons,
        "repaired_structure_context_ok": state in {STATE_CONTEXT, STATE_CONFIRMATION},
        "repaired_structure_confirmed": state == STATE_CONFIRMATION,
        "repaired_wait_state": state == STATE_WAIT,
        "repaired_conflict": state == STATE_CONFLICT,
        "repaired_no_structure": state == STATE_NO_STRUCTURE,
        "wait_not_entry_confirmation": bool(flags["wait_state"] and state != STATE_CONFIRMATION),
        "legacy_context_ok": bool(row.get("structure_context_ok")),
        "legacy_confirmed": bool(row.get("structure_confirmed")),
        "raw_buy_supply": flags["raw_buy_supply"],
        "raw_sell_demand": flags["raw_sell_demand"],
        "unmitigated_buy_supply": flags["unmitigated_buy_supply"],
        "unmitigated_sell_demand": flags["unmitigated_sell_demand"],
        "structure_bias_conflict": flags["bias_conflict"],
        "opposite_hard_confirmation": flags["opposite_hard"],
        "directional_hard_confirmation": flags["hard_confirmation"],
        "directional_context_signal": flags["directional_context"],
    }


def repair_structure_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.update(classify_structure_state(row))
        repaired.append(item)
    return repaired


def _gate(summary: dict[str, Any], settings: StructureContextRepairSettings) -> dict[str, Any]:
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
    checks["passes_candidate_gate"] = bool(checks["sample_ok"] and checks["expectancy_ok"] and checks["win_rate_ok"] and checks["loss_rate_ok"] and checks["time_exit_ok"])
    return checks


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: StructureContextRepairSettings, description: str) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    summary = _summarize_rows(selected)
    return {
        "name": name,
        "description": description,
        "gate_checks": _gate(summary, settings),
        "passes_candidate_gate": bool(_gate(summary, settings).get("passes_candidate_gate")),
        **summary,
    }


def _is_clean(row: dict[str, Any]) -> bool:
    return (not row.get("has_conflicting_patterns")) and bool(row.get("range_filter_ok"))


def _is_focus(row: dict[str, Any], settings: StructureContextRepairSettings) -> bool:
    return str(row.get("symbol") or "").upper() == settings.focus_symbol and str(row.get("bucket") or "").upper() == settings.focus_bucket


def _map_score_candidate(row: dict[str, Any], settings: StructureContextRepairSettings) -> bool:
    score = _safe_float(row.get("map_score"), 0.0)
    return settings.map_score_candidate_min <= score <= settings.map_score_candidate_max


def _is_bos_directional(row: dict[str, Any]) -> bool:
    state = str(row.get("structure_state") or "")
    side = str(row.get("side") or "").upper()
    if state == STATE_CONFLICT:
        return False
    if side == "BUY":
        return bool(row.get("bos_bullish"))
    if side == "SELL":
        return bool(row.get("bos_bearish"))
    return False


def _build_variants(rows: list[dict[str, Any]], settings: StructureContextRepairSettings) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = [
        _variant("all_repaired_rows", rows, lambda r: True, settings, "All structured rows after 29.5.0h relabeling."),
        _variant("legacy_structure_context_ok", rows, lambda r: bool(r.get("legacy_context_ok")), settings, "Legacy 29.5.0f/29.5.0g structure_context_ok."),
        _variant("repaired_context_or_confirmation", rows, lambda r: bool(r.get("repaired_structure_context_ok")), settings, "Rows relabeled as CONTEXT or CONFIRMATION."),
        _variant("repaired_confirmation_only", rows, lambda r: bool(r.get("repaired_structure_confirmed")), settings, "Rows relabeled as true directionally matching hard CONFIRMATION."),
        _variant("wait_states_watchlist_only", rows, lambda r: bool(r.get("repaired_wait_state")), settings, "WAIT states kept as watchlist-only, not entry confirmation."),
        _variant("conflict_rows_blocked", rows, lambda r: bool(r.get("repaired_conflict")), settings, "Rows explicitly blocked as structure conflicts."),
        _variant("clean_pattern_range_repaired_context", rows, lambda r: _is_clean(r) and bool(r.get("repaired_structure_context_ok")), settings, "Clean pattern/range candidates with repaired CONTEXT or CONFIRMATION."),
        _variant("clean_pattern_range_repaired_confirmation", rows, lambda r: _is_clean(r) and bool(r.get("repaired_structure_confirmed")), settings, "Clean pattern/range candidates with repaired hard CONFIRMATION."),
        _variant("map_score_65_79_repaired_context", rows, lambda r: _map_score_candidate(r, settings) and bool(r.get("repaired_structure_context_ok")), settings, "29.5.0g MAP_SCORE_65_79 hypothesis after repaired context rules."),
        _variant("bos_directional_repaired", rows, _is_bos_directional, settings, "Directionally matching BOS after conflict repair."),
        _variant("btc_focus_clean_repaired_context", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and bool(r.get("repaired_structure_context_ok")), settings, "BTC focus clean profile with repaired CONTEXT/CONFIRMATION."),
        _variant("btc_focus_clean_repaired_confirmation", rows, lambda r: _is_focus(r, settings) and _is_clean(r) and bool(r.get("repaired_structure_confirmed")), settings, "BTC focus clean profile with repaired hard CONFIRMATION."),
    ]
    for threshold in settings.score_thresholds:
        t = float(threshold)
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_repaired_context",
            rows,
            lambda r, t=t: _is_focus(r, settings) and _is_clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and bool(r.get("repaired_structure_context_ok")),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and repaired context.",
        ))
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_repaired_confirmation",
            rows,
            lambda r, t=t: _is_focus(r, settings) and _is_clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and bool(r.get("repaired_structure_confirmed")),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and repaired confirmation.",
        ))
    variants.sort(key=lambda v: (bool(v.get("passes_candidate_gate")), _safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)
    for idx, v in enumerate(variants, start=1):
        v["rank"] = idx
    return variants


def _component_quality(rows: list[dict[str, Any]], group_fn: Callable[[dict[str, Any]], str], *, min_candidates: int = 1) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(group_fn(r) or "NA")].append(r)
    out: list[dict[str, Any]] = []
    for key, vals in groups.items():
        if len(vals) < min_candidates:
            continue
        summary = _summarize_rows(vals)
        summary["component"] = key
        out.append(summary)
    out.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_float(x.get("win_rate_pct"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for idx, item in enumerate(out, start=1):
        item["rank"] = idx
    return out


def _transition_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    legacy_true = [r for r in rows if bool(r.get("legacy_context_ok"))]
    legacy_confirmed = [r for r in rows if bool(r.get("legacy_confirmed"))]
    state_counts = Counter(str(r.get("structure_state") or STATE_NO_STRUCTURE) for r in rows)
    legacy_to_state = Counter(str(r.get("structure_state") or STATE_NO_STRUCTURE) for r in legacy_true)
    confirmed_to_state = Counter(str(r.get("structure_state") or STATE_NO_STRUCTURE) for r in legacy_confirmed)
    return {
        "state_counts": dict(state_counts),
        "state_rate_pct": {k: round(_pct(v, len(rows)), 4) for k, v in state_counts.items()},
        "legacy_context_true_count": len(legacy_true),
        "legacy_context_to_repaired_state": dict(legacy_to_state),
        "legacy_confirmed_true_count": len(legacy_confirmed),
        "legacy_confirmed_to_repaired_state": dict(confirmed_to_state),
        "legacy_context_false_positive_wait_or_conflict": sum(1 for r in legacy_true if str(r.get("structure_state")) in {STATE_WAIT, STATE_CONFLICT, STATE_NO_STRUCTURE}),
        "legacy_confirmed_false_positive_wait_or_conflict": sum(1 for r in legacy_confirmed if str(r.get("structure_state")) in {STATE_WAIT, STATE_CONFLICT, STATE_NO_STRUCTURE}),
        "repaired_context_count": sum(1 for r in rows if bool(r.get("repaired_structure_context_ok"))),
        "repaired_confirmation_count": sum(1 for r in rows if bool(r.get("repaired_structure_confirmed"))),
        "wait_state_count": sum(1 for r in rows if bool(r.get("repaired_wait_state"))),
        "conflict_count": sum(1 for r in rows if bool(r.get("repaired_conflict"))),
    }


def _repair_failure_modes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    modes: dict[str, list[dict[str, Any]]] = {
        "wait_state_rejected_as_entry": [r for r in rows if bool(r.get("repaired_wait_state"))],
        "legacy_context_now_conflict": [r for r in rows if bool(r.get("legacy_context_ok")) and bool(r.get("repaired_conflict"))],
        "legacy_context_now_wait": [r for r in rows if bool(r.get("legacy_context_ok")) and bool(r.get("repaired_wait_state"))],
        "unmitigated_buy_in_supply": [r for r in rows if bool(r.get("unmitigated_buy_supply"))],
        "unmitigated_sell_in_demand": [r for r in rows if bool(r.get("unmitigated_sell_demand"))],
        "bias_conflict_blocked": [r for r in rows if bool(r.get("structure_bias_conflict"))],
        "opposite_hard_confirmation_blocked": [r for r in rows if bool(r.get("opposite_hard_confirmation"))],
        "no_structure_rejected": [r for r in rows if bool(r.get("repaired_no_structure"))],
    }
    out: dict[str, Any] = {}
    for name, vals in modes.items():
        out[name] = {
            "count": len(vals),
            "rate_pct": round(_pct(len(vals), len(rows)), 4),
            "summary": _summarize_rows(vals),
            "recent_examples": [
                {
                    "symbol": r.get("symbol"),
                    "datetime": r.get("datetime"),
                    "side": r.get("side"),
                    "bucket": r.get("bucket"),
                    "price_location": r.get("price_location"),
                    "structure_bias": r.get("structure_bias"),
                    "confirmation_summary": r.get("confirmation_summary"),
                    "structure_state": r.get("structure_state"),
                    "structure_repair_reasons": r.get("structure_repair_reasons"),
                    "outcome": r.get("outcome"),
                    "r": r.get("r"),
                }
                for r in vals[-5:]
            ],
        }
    return out


def _fallback_from_existing_reports(data_dir: Path) -> dict[str, Any]:
    paths = {
        "calibrated_structure_shadow": data_dir / "calibrated_structure_shadow_report.json",
        "structure_filter_diagnostics": data_dir / "structure_filter_diagnostics_report.json",
        "market_structure_map": data_dir / "market_structure_map_report.json",
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


def _settings_payload(settings: StructureContextRepairSettings) -> dict[str, Any]:
    return {
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "score_thresholds": list(settings.score_thresholds),
    }


def _decision(rows: list[dict[str, Any]], variants: list[dict[str, Any]], transitions: dict[str, Any], failures: dict[str, Any], fallback: dict[str, Any], settings: StructureContextRepairSettings) -> dict[str, Any]:
    if not rows and fallback.get("available"):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "Detailed rows unavailable; fallback reports cannot validate repaired structure labels.",
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "fallback_summary_only": True,
            "next_patch": "Rerun 29.5.0h locally with parquet support.",
        }
    passing = [v for v in variants if bool(v.get("passes_candidate_gate"))]
    passing_entry = [v for v in passing if v.get("name") not in {"wait_states_watchlist_only", "conflict_rows_blocked"}]
    best = variants[0] if variants else {}
    false_wait_conflict = _safe_int(transitions.get("legacy_context_false_positive_wait_or_conflict"), 0)
    repaired_confirmations = _safe_int(transitions.get("repaired_confirmation_count"), 0)
    reasons: list[str] = []
    if false_wait_conflict > 0:
        reasons.append("legacy structure_context_ok contained WAIT/CONFLICT/NO_STRUCTURE rows")
    if repaired_confirmations < settings.min_variant_candidates:
        reasons.append("repaired hard confirmations are still below minimum sample")
    if not passing_entry:
        reasons.append("no repaired entry-quality variant passed sample/expectancy/win/loss gates")
    if passing_entry:
        return {
            "status": "REPAIRED_FILTER_CANDIDATE_DIAGNOSTIC",
            "reason": "At least one repaired structure variant passed diagnostic gates, but operational unlock remains blocked pending independent validation.",
            "best_repaired_variant": passing_entry[0],
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "candidate_profile_status": "NON_OPERATIONAL_DIAGNOSTIC_ONLY",
            "next_patch": "29.5.0i repaired structure shadow validation / walk-forward quality audit before any paper unlock refinement",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "; ".join(reasons or ["repaired structure labels did not establish an unlockable edge"]),
        "best_repaired_variant": best,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "recommended_filter_actions": [
            "Use repaired_structure_context_ok instead of legacy structure_context_ok in future diagnostic variants.",
            "Treat PRICE_IN_DEMAND_WAIT_CONFIRMATION, PRICE_IN_SUPPLY_WAIT_CONFIRMATION and NEAR_LIQUIDITY_WAIT_REACTION as WAIT states, never as entry confirmation.",
            "Block BUY in supply and SELL in demand unless directionally matching hard confirmation exists.",
            "Block structure-bias conflicts unless directionally matching hard confirmation exists.",
            "Validate MAP_SCORE_65_79 and BOS components separately before paper unlock refinement.",
        ],
        "next_patch": "29.5.0i repaired structure shadow validation / MAP_SCORE_65_79 and BOS component audit, not paper unlock refinement yet",
    }


def build_structure_context_repair_report(data_dir: str | Path = "data", settings: StructureContextRepairSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or StructureContextRepairSettings.from_config()
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    fallback = _fallback_from_existing_reports(base) if not rows else {"available": False}
    variants = _build_variants(rows, settings) if rows else []
    transitions = _transition_matrix(rows) if rows else {}
    failures = _repair_failure_modes(rows) if rows else {}
    decision = _decision(rows, variants, transitions, failures, fallback, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "REPAIRED_FILTER_CANDIDATE_DIAGNOSTIC" else "WARN")

    report = {
        "report_type": "strict_structure_context_repair_confirmation_relabeling",
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
            "repair_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "repair_rules": {
            "CONFIRMATION": "confirmation_close plus directionally matching BOS/CHOCH/MSS/retest and no unmitigated directional conflict",
            "CONTEXT": "directional context without WAIT/CONFLICT and without hard confirmation",
            "WAIT": "PRICE_IN_DEMAND_WAIT_CONFIRMATION / PRICE_IN_SUPPLY_WAIT_CONFIRMATION / NEAR_LIQUIDITY_WAIT_REACTION; watchlist-only",
            "CONFLICT": "BUY in supply, SELL in demand, opposite bias/confirmation or failed retest unless mitigated by matching hard confirmation",
            "NO_STRUCTURE": "NO_STRUCTURAL_CONFIRMATION or no directional context",
        },
        "historical_summary": _summarize_rows(rows),
        "transition_matrix": transitions,
        "repair_variants": variants,
        "repair_variants_top": variants[:12],
        "component_quality": {
            "repaired_state_quality": _component_quality(rows, lambda r: str(r.get("structure_state") or STATE_NO_STRUCTURE), min_candidates=5),
            "relabel_quality": _component_quality(rows, lambda r: str(r.get("structure_relabel") or "NA"), min_candidates=5),
            "repair_reason_quality": _component_quality(rows, lambda r: "+".join(r.get("structure_repair_reasons") or ["NA"]), min_candidates=5),
        },
        "repair_failure_modes": failures,
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
                "structure_bias": r.get("structure_bias"),
                "price_location": r.get("price_location"),
                "confirmation_summary": r.get("confirmation_summary"),
                "legacy_context_ok": r.get("legacy_context_ok"),
                "legacy_confirmed": r.get("legacy_confirmed"),
                "structure_state": r.get("structure_state"),
                "structure_relabel": r.get("structure_relabel"),
                "structure_repair_reasons": r.get("structure_repair_reasons"),
                "repaired_structure_context_ok": r.get("repaired_structure_context_ok"),
                "repaired_structure_confirmed": r.get("repaired_structure_confirmed"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in rows[-20:]
        ],
        "files": {
            "report": str(base / REPORT_NAME),
            "calibrated_structure_shadow": str(base / "calibrated_structure_shadow_report.json"),
            "structure_filter_diagnostics": str(base / "structure_filter_diagnostics_report.json"),
            "market_structure_map": str(base / "market_structure_map_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_structure_context_repair_report(data_dir: str | Path = "data", settings: StructureContextRepairSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_structure_context_repair_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "StructureContextRepairSettings",
    "classify_structure_state",
    "repair_structure_rows",
    "build_structure_context_repair_report",
    "write_structure_context_repair_report",
]
