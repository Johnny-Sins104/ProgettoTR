"""Prompt 29.5.0g structure filter diagnostics / confirmation quality audit.

This module is a diagnostic-only audit layer after 29.5.0f.  It does not
propose an unlock profile and it never opens orders.  Its purpose is to explain
*why* structure filters did or did not improve scenario+pattern candidates by
measuring confirmation quality by component:

- confirmation_summary quality;
- price-location quality and direction conflicts;
- structure-bias alignment;
- liquidity/demand/supply/BOS/CHOCH/MSS/retest contribution;
- hard failure modes such as BUY in supply, SELL in demand, contradictory bias,
  missing confirmation and structure-confirmed variants with negative edge.

Safety invariant: no live, no testnet, no orders, no risk/threshold change, no
paper unlock mutation.  The output is ``structure_filter_diagnostics_report.json``.
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

REPORT_NAME = "structure_filter_diagnostics_report.json"
PROMPT_ID = "29.5.0g"
POSITIVE_OUTCOMES = {"TP1_ONLY", "TP2"}
NEGATIVE_OUTCOMES = {"SL"}


@dataclass(frozen=True)
class StructureFilterDiagnosticsSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_component_candidates: int = 20
    min_variant_candidates: int = 50
    min_expectancy_r: float = 0.10
    min_win_rate_pct: float = 52.0
    max_loss_rate_pct: float = 45.0
    max_time_exit_rate_pct: float = 60.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "StructureFilterDiagnosticsSettings":
        return cls(
            enabled=bool(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MAX_ROWS_PER_ASSET", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_EVAL_STRIDE", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_STRUCTURE_WINDOW_ROWS", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_component_candidates=max(5, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MIN_COMPONENT_CANDIDATES", 20), 20)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MIN_VARIANT_CANDIDATES", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_expectancy_r=_safe_float(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MIN_EXPECTANCY_R", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MIN_WIN_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MAX_LOSS_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "STRUCTURE_FILTER_DIAGNOSTICS_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
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
            score_thresholds=base.score_thresholds,
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


def _pct(n: float, d: float) -> float:
    return 0.0 if d <= 0 else n / d * 100.0


def _metrics(vals: Iterable[float]) -> dict[str, float]:
    values = sorted([_safe_float(v, float("nan")) for v in vals])
    values = [v for v in values if math.isfinite(v)]
    if not values:
        return {"count": 0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(q: float) -> float:
        if len(values) == 1:
            return values[0]
        idx = int(round((len(values) - 1) * q))
        return values[max(0, min(len(values) - 1, idx))]

    return {
        "count": len(values),
        "min": round(values[0], 8),
        "p25": round(pick(0.25), 8),
        "median": round(pick(0.50), 8),
        "p75": round(pick(0.75), 8),
        "max": round(values[-1], 8),
        "avg": round(float(mean(values)), 8),
    }


def _gate(summary: dict[str, Any], settings: StructureFilterDiagnosticsSettings) -> dict[str, Any]:
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


def _component_quality(rows: list[dict[str, Any]], group_fn: Callable[[dict[str, Any]], str], *, min_candidates: int = 1) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = str(group_fn(r) or "NA")
        groups[key].append(r)
    out: list[dict[str, Any]] = []
    for key, vals in groups.items():
        if len(vals) < min_candidates:
            continue
        s = _summarize_rows(vals)
        s["component"] = key
        out.append(s)
    out.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_float(x.get("win_rate_pct"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for idx, item in enumerate(out, start=1):
        item["rank"] = idx
    return out


def _side_bias_alignment(row: dict[str, Any]) -> str:
    side = str(row.get("side") or "").upper()
    bias = str(row.get("structure_bias") or "").upper()
    if side == "BUY" and bias.startswith("BULLISH"):
        return "ALIGNED_BULLISH_BUY"
    if side == "SELL" and bias.startswith("BEARISH"):
        return "ALIGNED_BEARISH_SELL"
    if side == "BUY" and bias.startswith("BEARISH"):
        return "CONFLICT_BEARISH_BUY"
    if side == "SELL" and bias.startswith("BULLISH"):
        return "CONFLICT_BULLISH_SELL"
    if bias.startswith("RANGING"):
        return "RANGING"
    return "UNKNOWN"


def _directional_conflict(row: dict[str, Any]) -> str:
    side = str(row.get("side") or "").upper()
    in_supply = bool(row.get("in_supply_zone")) or "SUPPLY" in str(row.get("price_location") or "").upper()
    in_demand = bool(row.get("in_demand_zone")) or "DEMAND" in str(row.get("price_location") or "").upper()
    if side == "BUY" and in_supply:
        return "BUY_IN_SUPPLY_OR_UPPER_SUPPLY"
    if side == "SELL" and in_demand:
        return "SELL_IN_DEMAND_OR_LOWER_DEMAND"
    if side == "BUY" and in_demand:
        return "BUY_IN_DEMAND"
    if side == "SELL" and in_supply:
        return "SELL_IN_SUPPLY"
    return "NO_ZONE_DIRECTION_CONFLICT"


def _confirmation_family(row: dict[str, Any]) -> str:
    summary = str(row.get("confirmation_summary") or "NA").upper()
    if "MSS" in summary:
        return "MSS"
    if "CHOCH" in summary:
        return "CHOCH"
    if "BOS" in summary:
        return "BOS"
    if "DEMAND" in summary:
        return "DEMAND_WAIT_CONFIRMATION"
    if "SUPPLY" in summary:
        return "SUPPLY_WAIT_CONFIRMATION"
    if "LIQUIDITY" in summary:
        return "NEAR_LIQUIDITY_WAIT_REACTION"
    if "NO_STRUCTURAL" in summary:
        return "NO_STRUCTURAL_CONFIRMATION"
    return summary or "NA"


def _map_score_bucket(row: dict[str, Any]) -> str:
    score = _safe_float(row.get("map_score"), 0.0)
    if score >= 80:
        return "MAP_SCORE_80_PLUS"
    if score >= 65:
        return "MAP_SCORE_65_79"
    if score >= 50:
        return "MAP_SCORE_50_64"
    if score >= 35:
        return "MAP_SCORE_35_49"
    return "MAP_SCORE_UNDER_35"


def _liquidity_context(row: dict[str, Any]) -> str:
    side = str(row.get("side") or "").upper()
    above = bool(row.get("liquidity_above_highs"))
    below = bool(row.get("liquidity_below_lows"))
    nearest = row.get("nearest_liquidity") if isinstance(row.get("nearest_liquidity"), dict) else {}
    nearest_side = str(nearest.get("side") or "").upper()
    if side == "BUY" and (below or nearest_side == "BELOW"):
        return "BUY_LIQUIDITY_BELOW"
    if side == "SELL" and (above or nearest_side == "ABOVE"):
        return "SELL_LIQUIDITY_ABOVE"
    if above or below:
        return "LIQUIDITY_PRESENT_OPPOSITE_OR_MIXED"
    return "NO_NEAR_LIQUIDITY"


def _strict_directional_context(row: dict[str, Any]) -> bool:
    side = str(row.get("side") or "").upper()
    bias = str(row.get("structure_bias") or "").upper()
    loc = str(row.get("price_location") or "").upper()
    in_supply = bool(row.get("in_supply_zone")) or "SUPPLY" in loc
    in_demand = bool(row.get("in_demand_zone")) or "DEMAND" in loc
    lower = "LOW" in loc or in_demand
    upper = "HIGH" in loc or in_supply
    bullish_break = bool(row.get("bos_bullish") or row.get("choch_bullish") or row.get("mss_bullish") or row.get("breakout_retest_confirmed"))
    bearish_break = bool(row.get("bos_bearish") or row.get("choch_bearish") or row.get("mss_bearish") or row.get("breakdown_retest_confirmed"))
    if side == "BUY":
        if in_supply and not bullish_break:
            return False
        if bias.startswith("BEARISH") and not bullish_break:
            return False
        return bool(in_demand or lower or bullish_break)
    if side == "SELL":
        if in_demand and not bearish_break:
            return False
        if bias.startswith("BULLISH") and not bearish_break:
            return False
        return bool(in_supply or upper or bearish_break)
    return False


def _hard_confirmation_directional(row: dict[str, Any]) -> bool:
    side = str(row.get("side") or "").upper()
    if not bool(row.get("confirmation_close")):
        return False
    if side == "BUY":
        return bool(row.get("bos_bullish") or row.get("choch_bullish") or row.get("mss_bullish") or row.get("breakout_retest_confirmed"))
    if side == "SELL":
        return bool(row.get("bos_bearish") or row.get("choch_bearish") or row.get("mss_bearish") or row.get("breakdown_retest_confirmed"))
    return False


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: StructureFilterDiagnosticsSettings, description: str) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    summary = _summarize_rows(selected)
    return {
        "name": name,
        "description": description,
        "gate_checks": _gate(summary, settings),
        **summary,
    }


def _build_audit_variants(rows: list[dict[str, Any]], settings: StructureFilterDiagnosticsSettings) -> list[dict[str, Any]]:
    focus = lambda r: str(r.get("symbol") or "").upper() == settings.focus_symbol and str(r.get("bucket") or "").upper() == settings.focus_bucket
    clean = lambda r: (not r.get("has_conflicting_patterns")) and bool(r.get("range_filter_ok"))
    variants = [
        _variant("all_structured_candidates", rows, lambda r: True, settings, "All scenario+pattern candidates with structure diagnostics."),
        _variant("legacy_structure_context_ok", rows, lambda r: bool(r.get("structure_context_ok")), settings, "29.5.0f constructive structure context flag."),
        _variant("strict_directional_context", rows, _strict_directional_context, settings, "Directional context excluding BUY in supply / SELL in demand unless a directional break exists."),
        _variant("hard_confirmation_directional", rows, _hard_confirmation_directional, settings, "confirmation_close plus directionally matching BOS/CHOCH/MSS/retest."),
        _variant("clean_pattern_range_strict_context", rows, lambda r: clean(r) and _strict_directional_context(r), settings, "Clean pattern/range candidates plus strict directional context."),
        _variant("btc_focus_clean_strict_context", rows, lambda r: focus(r) and clean(r) and _strict_directional_context(r), settings, "BTC focus profile after clean pattern/range plus strict directional context."),
        _variant("btc_focus_clean_hard_confirmation", rows, lambda r: focus(r) and clean(r) and _hard_confirmation_directional(r), settings, "BTC focus profile with hard directionally matching structural confirmation."),
    ]
    variants.sort(key=lambda v: (_safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)
    for idx, v in enumerate(variants, start=1):
        v["rank"] = idx
    return variants


def _failure_modes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    modes: dict[str, list[dict[str, Any]]] = {
        "buy_in_supply": [r for r in rows if str(r.get("side") or "").upper() == "BUY" and (bool(r.get("in_supply_zone")) or "SUPPLY" in str(r.get("price_location") or "").upper())],
        "sell_in_demand": [r for r in rows if str(r.get("side") or "").upper() == "SELL" and (bool(r.get("in_demand_zone")) or "DEMAND" in str(r.get("price_location") or "").upper())],
        "bias_conflict": [r for r in rows if _side_bias_alignment(r).startswith("CONFLICT")],
        "context_ok_but_direction_conflict": [r for r in rows if bool(r.get("structure_context_ok")) and _directional_conflict(r) in {"BUY_IN_SUPPLY_OR_UPPER_SUPPLY", "SELL_IN_DEMAND_OR_LOWER_DEMAND"}],
        "hard_confirmed_but_losing": [r for r in rows if _hard_confirmation_directional(r) and _safe_float(r.get("r"), 0.0) < 0],
        "no_structural_confirmation": [r for r in rows if "NO_STRUCTURAL" in str(r.get("confirmation_summary") or "").upper()],
        "near_liquidity_wait_reaction": [r for r in rows if "LIQUIDITY" in str(r.get("confirmation_summary") or "").upper()],
    }
    return {
        name: {
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
                    "r": r.get("r"),
                    "outcome": r.get("outcome"),
                }
                for r in vals[-5:]
            ],
        }
        for name, vals in modes.items()
    }


def _decision(rows: list[dict[str, Any]], variants: list[dict[str, Any]], failures: dict[str, Any], settings: StructureFilterDiagnosticsSettings, fallback: dict[str, Any]) -> dict[str, Any]:
    if not rows and fallback.get("available"):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "Detailed rows unavailable; fallback reports are insufficient for filter unlock.",
            "operational_unlock_allowed": False,
            "next_patch": "Rerun 29.5.0g locally with parquet support, or collect more structure-confirmed rows.",
            "fallback_summary_only": True,
        }
    best = variants[0] if variants else {}
    conflict_rate = _safe_float((failures.get("context_ok_but_direction_conflict") or {}).get("rate_pct"), 0.0)
    hard_confirmed = next((v for v in variants if v.get("name") == "hard_confirmation_directional"), {})
    focus_hard = next((v for v in variants if v.get("name") == "btc_focus_clean_hard_confirmation"), {})
    reasons: list[str] = []
    if conflict_rate > 5.0:
        reasons.append("legacy structure_context_ok admits directional conflicts")
    if _safe_int(hard_confirmed.get("candidates"), 0) < settings.min_variant_candidates:
        reasons.append("hard structural confirmation sample is too small")
    if _safe_float(hard_confirmed.get("expectancy_r"), 0.0) < 0.0:
        reasons.append("hard structural confirmation is negative in the sampled rows")
    if _safe_int(focus_hard.get("candidates"), 0) == 0:
        reasons.append("BTC focus has zero hard-confirmed rows")
    if not reasons:
        reasons.append("no variant passed candidate gates")
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "; ".join(reasons),
        "best_audit_variant": best,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "recommended_filter_actions": [
            "Make structure_context directional: exclude BUY in supply and SELL in demand unless BOS/CHOCH/MSS/retest confirms that direction.",
            "Separate WAIT states from true confirmations: PRICE_IN_DEMAND_WAIT_CONFIRMATION and PRICE_IN_SUPPLY_WAIT_CONFIRMATION should not be treated as entry confirmation.",
            "Audit hard confirmation quality before using BOS/CHOCH/MSS as a gate; current confirmed sample is small or weak.",
            "Collect more BTC BUY_REJECTION rows with actual bullish confirmation before paper unlock refinement.",
            "Keep all structure filters diagnostic until a variant passes sample, expectancy, win-rate and loss-rate gates.",
        ],
        "next_patch": "29.5.0h strict structure context repair / confirmation relabeling, not 29.4.4c paper unlock refinement",
    }


def _fallback_from_existing_reports(data_dir: Path) -> dict[str, Any]:
    css_path = data_dir / "calibrated_structure_shadow_report.json"
    msm_path = data_dir / "market_structure_map_report.json"
    out: dict[str, Any] = {"available": False}
    for name, path in (("calibrated_structure_shadow", css_path), ("market_structure_map", msm_path)):
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


def _settings_payload(settings: StructureFilterDiagnosticsSettings) -> dict[str, Any]:
    return {
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_component_candidates": settings.min_component_candidates,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
    }


def build_structure_filter_diagnostics_report(data_dir: str | Path = "data", settings: StructureFilterDiagnosticsSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or StructureFilterDiagnosticsSettings.from_config()
    if not settings.enabled:
        rows: list[dict[str, Any]] = []
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = list(historical.get("candidate_rows") or [])
    fallback = _fallback_from_existing_reports(base) if not rows else {"available": False}
    components = {
        "confirmation_summary_quality": _component_quality(rows, lambda r: str(r.get("confirmation_summary") or "NA"), min_candidates=settings.min_component_candidates),
        "confirmation_family_quality": _component_quality(rows, _confirmation_family, min_candidates=settings.min_component_candidates),
        "price_location_quality": _component_quality(rows, lambda r: str(r.get("price_location") or "NA"), min_candidates=settings.min_component_candidates),
        "structure_bias_alignment_quality": _component_quality(rows, _side_bias_alignment, min_candidates=settings.min_component_candidates),
        "directional_zone_conflict_quality": _component_quality(rows, _directional_conflict, min_candidates=settings.min_component_candidates),
        "liquidity_context_quality": _component_quality(rows, _liquidity_context, min_candidates=settings.min_component_candidates),
        "map_score_bucket_quality": _component_quality(rows, _map_score_bucket, min_candidates=settings.min_component_candidates),
    }
    variants = _build_audit_variants(rows, settings) if rows else []
    failures = _failure_modes(rows) if rows else {}
    decision = _decision(rows, variants, failures, settings, fallback)
    status = "DISABLED" if not settings.enabled else "WARN"
    report = {
        "report_type": "structure_filter_diagnostics_confirmation_quality_audit",
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
            "audit_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "historical_summary": _summarize_rows(rows),
        "audit_variants": variants,
        "audit_variants_top": variants[:12],
        "component_quality": components,
        "failure_modes": failures,
        "by_asset": historical.get("by_asset", {}),
        "fallback": fallback,
        "warnings": historical.get("warnings", []),
        "files": {
            "report": str(base / REPORT_NAME),
            "calibrated_structure_shadow": str(base / "calibrated_structure_shadow_report.json"),
            "market_structure_map": str(base / "market_structure_map_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_structure_filter_diagnostics_report(data_dir: str | Path = "data", settings: StructureFilterDiagnosticsSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_structure_filter_diagnostics_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "StructureFilterDiagnosticsSettings",
    "build_structure_filter_diagnostics_report",
    "write_structure_filter_diagnostics_report",
]
