"""Prompt 29.4.3 shadow threshold simulation utilities.

This module is diagnostic-only.  It reads paper event logs and signal
 diagnostics, simulates alternate paper-only entry gates, and writes an operator
 report.  It never changes strategy decisions, risk, orders, positions, broker
 state, Telegram control, live mode, or testnet behavior.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import json
import math

from config import Config
from core.paper_signal_diagnostics import (
    DIAGNOSTIC_EVENT_TYPE,
    _event_key,
    cycle_seq,
    infer_legacy_no_signal_diagnostic,
    read_jsonl,
    safe_float,
)

SHADOW_REPORT_NAME = "paper_shadow_unlock_report.json"


@dataclass(frozen=True)
class ShadowProfile:
    name: str
    min_ai_prob: float
    min_setup_quality: float
    min_abs_tech_score: float | None = None
    asset_filter: tuple[str, ...] = ()
    include_structural_filters: bool = False
    include_inferred: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _pct(num: float, den: float) -> float:
    return 0.0 if den <= 0 else num / den * 100.0


def _default_profiles() -> list[ShadowProfile]:
    return [
        ShadowProfile("CURRENT_GATES", 55.0, 50.0),
        ShadowProfile("CONSERVATIVE_45_Q60", 45.0, 60.0),
        ShadowProfile("CONSERVATIVE_40_Q60", 40.0, 60.0),
        ShadowProfile("CONSERVATIVE_35_Q60", 35.0, 60.0),
        ShadowProfile("BTC_ONLY_40_Q60", 40.0, 60.0, asset_filter=("BTC/USDT",)),
        ShadowProfile("BTC_ONLY_35_Q60", 35.0, 60.0, asset_filter=("BTC/USDT",)),
    ]


def _load_combined_diagnostics(events: list[dict[str, Any]], *, include_inferred: bool = True) -> list[dict[str, Any]]:
    exact = [e for e in events if str(e.get("event_type") or "").upper() == DIAGNOSTIC_EVENT_TYPE]
    exact_keys = {_event_key(e) for e in exact}
    rows: list[dict[str, Any]] = []
    for e in exact:
        row = dict(e)
        row["exact"] = True
        row["inferred"] = False
        row.setdefault("cycle_seq", cycle_seq(row.get("cycle_id")))
        row.setdefault("abs_technical_score", abs(safe_float(row.get("technical_score"), 0.0)))
        rows.append(row)
    if include_inferred:
        for e in events:
            if str(e.get("event_type") or "").upper() != "NO_SIGNAL":
                continue
            if _event_key(e) in exact_keys:
                continue
            rows.append(infer_legacy_no_signal_diagnostic(e))
    return rows


def _price_series(events: list[dict[str, Any]]) -> tuple[dict[tuple[str, str, str], float], dict[str, list[dict[str, Any]]]]:
    by_key: dict[tuple[str, str, str], float] = {}
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        if str(e.get("event_type") or "").upper() != "ASSET_SCANNED":
            continue
        symbol = str(e.get("symbol") or "UNKNOWN")
        candle_ts = str(e.get("candle_ts") or "")
        cid = str(e.get("cycle_id") or "")
        price = safe_float(e.get("last_price"), 0.0)
        if price <= 0:
            continue
        seq = cycle_seq(cid)
        row = {"symbol": symbol, "cycle_id": cid, "cycle_seq": seq, "candle_ts": candle_ts, "ts": e.get("ts"), "price": price}
        by_key[(cid, symbol, candle_ts)] = price
        by_symbol[symbol].append(row)
    for symbol in list(by_symbol):
        by_symbol[symbol] = sorted(by_symbol[symbol], key=lambda r: (_safe_int(r.get("cycle_seq"), -1), str(r.get("ts") or "")))
    return by_key, by_symbol


STRUCTURAL_FILTERS = {
    "RANGE_POSITION_FILTERED",
    "MTF_FILTERED",
    "TREND_ALIGNMENT_FILTERED",
    "DUPLICATE_CANDLE",
}


def _candidate_matches_profile(row: dict[str, Any], profile: ShadowProfile) -> tuple[bool, str]:
    symbol = str(row.get("symbol") or "UNKNOWN")
    if profile.asset_filter and symbol not in set(profile.asset_filter):
        return False, "asset_filter"
    if not profile.include_inferred and _bool(row.get("inferred")):
        return False, "inferred_disabled"
    side = str(row.get("intended_side") or "HOLD").upper()
    if side not in {"BUY", "SELL"}:
        return False, "no_intended_side"
    dominant_filter = str(row.get("dominant_filter") or "UNKNOWN").upper()
    if not profile.include_structural_filters and dominant_filter in STRUCTURAL_FILTERS:
        return False, f"structural_filter:{dominant_filter}"
    ai_prob = safe_float(row.get("ai_prob"), 0.0)
    if ai_prob < profile.min_ai_prob:
        return False, "ai_prob_low"
    setup_quality = safe_float(row.get("setup_quality"), 0.0)
    if setup_quality < profile.min_setup_quality:
        return False, "setup_quality_low"
    abs_score = abs(safe_float(row.get("technical_score"), safe_float(row.get("abs_technical_score"), 0.0)))
    active_threshold = safe_float((row.get("thresholds") or {}).get("active_score_threshold"), 30.0)
    min_abs = profile.min_abs_tech_score if profile.min_abs_tech_score is not None else active_threshold
    if abs_score < float(min_abs):
        return False, "tech_score_low"
    return True, "matched"


def _candidate_entry_price(row: dict[str, Any], price_by_key: dict[tuple[str, str, str], float]) -> float:
    direct = safe_float(row.get("last_price"), 0.0)
    if direct > 0:
        return direct
    key = (str(row.get("cycle_id") or ""), str(row.get("symbol") or "UNKNOWN"), str(row.get("candle_ts") or ""))
    return safe_float(price_by_key.get(key), 0.0)


def _simulate_candidate(
    row: dict[str, Any],
    *,
    entry_price: float,
    future_prices: list[dict[str, Any]],
    max_hold_cycles: int,
    stop_loss_pct: float,
    tp1_pct: float,
    tp2_pct: float,
) -> dict[str, Any]:
    side = str(row.get("intended_side") or "HOLD").upper()
    entry_seq = _safe_int(row.get("cycle_seq") if row.get("cycle_seq") is not None else cycle_seq(row.get("cycle_id")), -1)
    future = [p for p in future_prices if _safe_int(p.get("cycle_seq"), -1) > entry_seq]
    if max_hold_cycles > 0:
        future = future[:max_hold_cycles]
    if not future:
        return {"outcome": "NO_FUTURE_DATA", "status": "skipped", "simulated": False}

    mfe_pct = 0.0
    mae_pct = 0.0
    first_tp1: dict[str, Any] | None = None
    first_tp2: dict[str, Any] | None = None
    first_sl: dict[str, Any] | None = None
    last_ret_pct = 0.0
    last_point = future[-1]

    for p in future:
        price = safe_float(p.get("price"), 0.0)
        if price <= 0 or entry_price <= 0:
            continue
        raw_ret = (price - entry_price) / entry_price
        ret = raw_ret if side == "BUY" else -raw_ret
        ret_pct = ret * 100.0
        last_ret_pct = ret_pct
        mfe_pct = max(mfe_pct, ret_pct)
        mae_pct = min(mae_pct, ret_pct)
        if first_sl is None and ret <= -abs(stop_loss_pct):
            first_sl = p
            break
        if first_tp2 is None and ret >= abs(tp2_pct):
            first_tp2 = p
            break
        if first_tp1 is None and ret >= abs(tp1_pct):
            first_tp1 = p
            break

    if first_sl is not None:
        outcome = "SL"
        exit_point = first_sl
        pnl_r = -1.0
        exit_pct = -abs(stop_loss_pct) * 100.0
    elif first_tp2 is not None:
        outcome = "TP2"
        exit_point = first_tp2
        pnl_r = abs(tp2_pct) / abs(stop_loss_pct) if stop_loss_pct else 0.0
        exit_pct = abs(tp2_pct) * 100.0
    elif first_tp1 is not None:
        outcome = "TP1"
        exit_point = first_tp1
        pnl_r = abs(tp1_pct) / abs(stop_loss_pct) if stop_loss_pct else 0.0
        exit_pct = abs(tp1_pct) * 100.0
    else:
        outcome = "EXPIRED"
        exit_point = last_point
        pnl_r = (last_ret_pct / 100.0) / abs(stop_loss_pct) if stop_loss_pct else 0.0
        exit_pct = last_ret_pct

    return {
        "outcome": outcome,
        "status": "simulated",
        "simulated": True,
        "entry_price": round(entry_price, 8),
        "exit_price": round(safe_float(exit_point.get("price"), 0.0), 8),
        "exit_cycle_seq": exit_point.get("cycle_seq"),
        "exit_candle_ts": exit_point.get("candle_ts"),
        "hold_steps": max(0, _safe_int(exit_point.get("cycle_seq"), entry_seq) - entry_seq),
        "pnl_pct": round(exit_pct, 6),
        "pnl_r": round(pnl_r, 6),
        "mfe_pct": round(mfe_pct, 6),
        "mae_pct": round(mae_pct, 6),
    }


def _summarize_profile(name: str, rows: list[dict[str, Any]], *, reject_reasons: Counter[str]) -> dict[str, Any]:
    simulated = [r for r in rows if r.get("simulation", {}).get("simulated") is True]
    outcomes = Counter(str((r.get("simulation") or {}).get("outcome") or "UNKNOWN") for r in rows)
    winners = [r for r in simulated if str((r.get("simulation") or {}).get("outcome")) in {"TP1", "TP2"}]
    pnl_rs = [safe_float((r.get("simulation") or {}).get("pnl_r"), 0.0) for r in simulated]
    by_asset = Counter(str(r.get("symbol") or "UNKNOWN") for r in simulated)
    by_side = Counter(str(r.get("intended_side") or "UNKNOWN") for r in simulated)
    mfe_vals = [safe_float((r.get("simulation") or {}).get("mfe_pct"), 0.0) for r in simulated]
    mae_vals = [safe_float((r.get("simulation") or {}).get("mae_pct"), 0.0) for r in simulated]
    return {
        "profile": name,
        "candidate_rows": len(rows),
        "simulated_rows": len(simulated),
        "no_future_data": outcomes.get("NO_FUTURE_DATA", 0),
        "outcomes": dict(outcomes.most_common()),
        "win_rate_pct": round(_pct(len(winners), len(simulated)), 4) if simulated else 0.0,
        "expectancy_r": round(mean(pnl_rs), 6) if pnl_rs else 0.0,
        "total_r": round(sum(pnl_rs), 6) if pnl_rs else 0.0,
        "avg_mfe_pct": round(mean(mfe_vals), 6) if mfe_vals else 0.0,
        "avg_mae_pct": round(mean(mae_vals), 6) if mae_vals else 0.0,
        "by_asset": dict(by_asset.most_common()),
        "by_side": dict(by_side.most_common()),
        "reject_reasons": dict(reject_reasons.most_common()),
        "top_shadow_trades": sorted(
            rows,
            key=lambda r: (
                safe_float((r.get("simulation") or {}).get("pnl_r"), -99.0),
                safe_float(r.get("setup_quality"), 0.0),
                safe_float(r.get("ai_prob"), 0.0),
            ),
            reverse=True,
        )[:12],
    }


def build_shadow_unlock_report(data_dir: str | Path) -> dict[str, Any]:
    data_path = Path(data_dir)
    events_path = data_path / "paper_events.jsonl"
    events = read_jsonl(events_path)
    price_by_key, prices_by_symbol = _price_series(events)
    include_inferred = bool(getattr(Config, "PAPER_SHADOW_INCLUDE_INFERRED", True))
    diagnostics = _load_combined_diagnostics(events, include_inferred=include_inferred)
    profiles = _default_profiles()

    max_hold_cycles = int(getattr(Config, "PAPER_SHADOW_MAX_HOLD_CYCLES", 12))
    stop_loss_pct = float(getattr(Config, "PAPER_SHADOW_STOP_LOSS_PCT", 0.0035))
    tp1_pct = float(getattr(Config, "PAPER_SHADOW_TP1_PCT", 0.0035))
    tp2_pct = float(getattr(Config, "PAPER_SHADOW_TP2_PCT", 0.0070))

    profile_reports: dict[str, Any] = {}
    all_shadow_rows: list[dict[str, Any]] = []
    for profile in profiles:
        matched: list[dict[str, Any]] = []
        reject_reasons: Counter[str] = Counter()
        for row in diagnostics:
            ok, reason = _candidate_matches_profile(row, profile)
            if not ok:
                reject_reasons[reason] += 1
                continue
            entry_price = _candidate_entry_price(row, price_by_key)
            if entry_price <= 0:
                reject_reasons["missing_entry_price"] += 1
                continue
            symbol = str(row.get("symbol") or "UNKNOWN")
            sim = _simulate_candidate(
                row,
                entry_price=entry_price,
                future_prices=prices_by_symbol.get(symbol, []),
                max_hold_cycles=max_hold_cycles,
                stop_loss_pct=stop_loss_pct,
                tp1_pct=tp1_pct,
                tp2_pct=tp2_pct,
            )
            compact = {
                "profile": profile.name,
                "symbol": symbol,
                "cycle_id": row.get("cycle_id"),
                "cycle_seq": row.get("cycle_seq"),
                "candle_ts": row.get("candle_ts"),
                "exact": bool(row.get("exact") is True),
                "inferred": bool(row.get("inferred") is True),
                "confidence_level": row.get("confidence_level", "exact" if row.get("exact") else "unknown"),
                "intended_side": str(row.get("intended_side") or "HOLD").upper(),
                "dominant_filter": row.get("dominant_filter"),
                "technical_score": round(safe_float(row.get("technical_score"), 0.0), 6),
                "abs_technical_score": round(abs(safe_float(row.get("technical_score"), safe_float(row.get("abs_technical_score"), 0.0))), 6),
                "ai_prob": round(safe_float(row.get("ai_prob"), 0.0), 8),
                "setup_quality": round(safe_float(row.get("setup_quality"), 0.0), 8),
                "entry_price": round(entry_price, 8),
                "simulation": sim,
            }
            matched.append(compact)
            all_shadow_rows.append(compact)
        profile_reports[profile.name] = _summarize_profile(profile.name, matched, reject_reasons=reject_reasons)

    recommendations: list[str] = []
    viable_profiles = [p for p in profile_reports.values() if int(p.get("simulated_rows") or 0) >= 3]
    positive_profiles = [p for p in viable_profiles if safe_float(p.get("expectancy_r"), 0.0) > 0.0]
    if not all_shadow_rows:
        recommendations.append("No shadow candidates matched the configured threshold profiles. Keep current gates and collect more diagnostics.")
    elif not viable_profiles:
        recommendations.append("Shadow candidates exist, but sample size is too small for any unlock decision.")
    elif positive_profiles:
        best = sorted(positive_profiles, key=lambda p: (safe_float(p.get("expectancy_r"), 0.0), int(p.get("simulated_rows") or 0)), reverse=True)[0]
        recommendations.append(f"Best positive shadow profile is {best.get('profile')} with expectancy_r={best.get('expectancy_r')} over {best.get('simulated_rows')} simulated rows; validate with more data before any unlock.")
    else:
        recommendations.append("No profile shows positive shadow expectancy. Do not unlock entries yet.")
    recommendations.append("This report is shadow-only: it does not place orders, alter thresholds, or change paper/live execution.")

    event_counts = Counter(str(e.get("event_type") or "").upper() for e in events)
    return {
        "generated_at": utc_now_iso(),
        "status": "WARN" if not positive_profiles else "PASS",
        "shadow_only": True,
        "diagnostic_only": True,
        "strategy_changed": False,
        "paper_entry_unlock_enabled": False,
        "live_execution_enabled": False,
        "runtime_files": {
            "events": str(events_path),
            "report": str(data_path / SHADOW_REPORT_NAME),
        },
        "simulation_model": {
            "price_source": "ASSET_SCANNED.last_price close/mark proxy",
            "entry_price_source": "diagnostic.last_price or matching ASSET_SCANNED.last_price",
            "max_hold_cycles": max_hold_cycles,
            "stop_loss_pct": stop_loss_pct,
            "tp1_pct": tp1_pct,
            "tp2_pct": tp2_pct,
            "notes": [
                "Close/mark-only simulation; it does not model intrabar path, slippage, partial fills, or exchange microstructure.",
                "TP1 is treated as conservative first-profit exit when touched before TP2/SL.",
            ],
        },
        "counts": {
            "events_total": len(events),
            "asset_scanned": event_counts.get("ASSET_SCANNED", 0),
            "diagnostics_loaded": len(diagnostics),
            "exact_diagnostics_loaded": sum(1 for r in diagnostics if r.get("exact") is True),
            "inferred_diagnostics_loaded": sum(1 for r in diagnostics if r.get("inferred") is True),
            "shadow_rows_total": len(all_shadow_rows),
            "signals_detected": event_counts.get("SIGNAL_DETECTED", 0),
            "orders_submitted": event_counts.get("PAPER_ORDER_SUBMITTED", 0),
            "positions_opened": event_counts.get("POSITION_OPENED", 0),
        },
        "profiles": profile_reports,
        "top_shadow_rows": sorted(
            all_shadow_rows,
            key=lambda r: (
                safe_float((r.get("simulation") or {}).get("pnl_r"), -99.0),
                safe_float(r.get("setup_quality"), 0.0),
                safe_float(r.get("ai_prob"), 0.0),
            ),
            reverse=True,
        )[:30],
        "recommendations": recommendations,
    }


def write_shadow_unlock_report(data_dir: str | Path) -> dict[str, Any]:
    path = Path(data_dir) / SHADOW_REPORT_NAME
    report = build_shadow_unlock_report(data_dir)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
