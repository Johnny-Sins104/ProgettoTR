"""Prompt 29.4.4s-7b — LSR-v2 trade forensics.

Diagnostic-only attribution layer for the Prompt 29.4.4s-7 LSR-v2
backtest matrix.  It reads simulated trade JSONL files and backtest reports,
then explains whether the apparent edge is low-sample, outlier-dominated, or
cost-sensitive.  It never routes signals, calls brokers, submits orders, opens
positions, mutates paper state, or enables live/testnet/exchange broker paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math
import statistics

PROMPT_ID = "29.4.4s-7b"
TRADE_EVENT_TYPE = "LSR_V2_BACKTEST_TRADE"
FORENSICS_REPORT_NAME = "lsr_v2_trade_forensics_report.json"
BY_WINDOW_REPORT_NAME = "lsr_v2_trade_forensics_by_window.json"
COST_FAILURE_REPORT_NAME = "lsr_v2_cost_failure_attribution_report.json"
MATRIX_REPORT_NAME = "lsr_v2_backtest_matrix_report.json"
COST_STRESS_REPORT_NAME = "lsr_v2_cost_stress_report.json"
TRADE_FILE_PREFIX = "lsr_v2_trades"

READY_DECISION = "LSR_V2_FORENSICS_READY_DIAGNOSTIC"
FRAGILE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FORENSICS_NO_TRADES"
LOAD_ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FORENSICS_ERROR"

PRIMARY_COST_MODEL = "conservative"
SEVERE_COST_MODEL = "severe"
DEFAULT_WINDOWS = (10_000, 12_000, 15_000, 18_000, 20_000, 30_000, 50_000)
DEFAULT_PRIMARY_WINDOWS = (10_000, 12_000, 15_000, 18_000, 20_000)


@dataclass(frozen=True)
class LSRV2TradeForensicsSettings:
    data_dir: str = "data"
    windows: tuple[int, ...] = DEFAULT_WINDOWS
    primary_windows: tuple[int, ...] = DEFAULT_PRIMARY_WINDOWS
    primary_cost_model: str = PRIMARY_COST_MODEL
    severe_cost_model: str = SEVERE_COST_MODEL
    min_closed_trades: int = 30
    preferred_closed_trades: int = 50
    min_positive_windows: int = 3
    breakeven_r_abs: float = 0.10
    max_top1_positive_concentration: float = 0.45
    max_top3_positive_concentration: float = 0.80
    max_top5_positive_concentration: float = 0.90
    max_top1_net_contribution: float = 0.65
    severe_degradation_warn_r: float = 3.0
    cost_flip_warn_ratio: float = 0.20
    report_all_cost_models: bool = True

    @classmethod
    def default(cls) -> "LSRV2TradeForensicsSettings":
        return cls()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_div(num: float, den: float, default: float | None = None) -> float | None:
    try:
        den = float(den)
        if abs(den) <= 1e-12:
            return default
        out = float(num) / den
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _round(value: Any, digits: int = 8) -> float | None:
    try:
        out = float(value)
        if math.isfinite(out):
            return round(out, digits)
    except Exception:
        pass
    return None


def _avg(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _median(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return None
    return float(statistics.median(vals))


def _percentile(values: Sequence[float], pct: float) -> float | None:
    vals = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * max(0.0, min(1.0, pct))
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - k) + vals[hi] * (k - lo)


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        p = Path(path)
        if not p.exists():
            return {}
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return rows
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except Exception:
        return rows
    return rows


def parse_windows(raw: str | Sequence[int] | None) -> tuple[int, ...]:
    if raw is None:
        return DEFAULT_WINDOWS
    if isinstance(raw, str):
        vals: list[int] = []
        for token in raw.split(","):
            token = token.strip().lower().replace("_", "")
            if not token:
                continue
            mult = 1000 if token.endswith("k") else 1
            if token.endswith("k"):
                token = token[:-1]
            try:
                vals.append(int(float(token) * mult))
            except Exception:
                continue
        return tuple(dict.fromkeys(v for v in vals if v > 0)) or DEFAULT_WINDOWS
    return tuple(dict.fromkeys(int(v) for v in raw if int(v) > 0)) or DEFAULT_WINDOWS


def _window_label(size: int) -> str:
    if int(size) % 1000 == 0:
        return f"{int(size) // 1000}k"
    return str(int(size))


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _count_by(rows: Sequence[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        val = str(row.get(key, "UNKNOWN") or "UNKNOWN")
        out[val] = out.get(val, 0) + 1
    return dict(sorted(out.items()))


def _trade_key(row: dict[str, Any]) -> str:
    # candidate_id is stable inside one window/cost file.  Entry/exit fields are
    # retained to avoid accidental collision if a future simulator changes ids.
    fields = (
        row.get("candidate_id"),
        row.get("window_label"),
        row.get("window_size"),
        row.get("side"),
        row.get("entry_index"),
        row.get("entry_timestamp"),
        row.get("entry_price"),
        row.get("stop_loss"),
        row.get("take_profit"),
    )
    return "|".join(str(x) for x in fields)


def _load_trade_files(data_dir: Path, settings: LSRV2TradeForensicsSettings) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    trades: list[dict[str, Any]] = []
    files: dict[str, str] = {}
    missing: list[str] = []
    for size in settings.windows:
        label = _window_label(size)
        path = data_dir / f"{TRADE_FILE_PREFIX}_{label}.jsonl"
        if not path.exists():
            missing.append(str(path))
            continue
        loaded = _read_jsonl(path)
        for row in loaded:
            row.setdefault("window_label", label)
            row.setdefault("window_size", int(size))
        trades.extend(loaded)
        files[label] = str(path)
    # Fallback: if explicit windows missed custom labels, read all LSR files.
    if not trades:
        for path in sorted(data_dir.glob(f"{TRADE_FILE_PREFIX}_*.jsonl")):
            loaded = _read_jsonl(path)
            for row in loaded:
                if not row.get("window_label"):
                    row["window_label"] = path.stem.replace(f"{TRADE_FILE_PREFIX}_", "")
            trades.extend(loaded)
            files[path.stem.replace(f"{TRADE_FILE_PREFIX}_", "")] = str(path)
    return trades, files, missing


def _summarize_trades(trades: Sequence[dict[str, Any]], settings: LSRV2TradeForensicsSettings) -> dict[str, Any]:
    r_values = [_safe_float(t.get("net_r"), 0.0) for t in trades]
    gross_values = [_safe_float(t.get("gross_r"), 0.0) for t in trades]
    cost_values = [_safe_float(t.get("cost_r"), 0.0) for t in trades]
    pnl_values = [_safe_float(t.get("net_pnl"), 0.0) for t in trades]
    wins = [r for r in r_values if r > settings.breakeven_r_abs]
    losses = [r for r in r_values if r < -settings.breakeven_r_abs]
    breakevens = [r for r in r_values if -settings.breakeven_r_abs <= r <= settings.breakeven_r_abs]
    positives = sorted([r for r in r_values if r > 0], reverse=True)
    positive_sum = sum(positives)
    negative_sum = abs(sum(r for r in r_values if r < 0))
    net_sum = sum(r_values)
    top1 = positives[0] if positives else 0.0
    top3 = sum(positives[:3])
    top5 = sum(positives[:5])
    top1_pos_conc = _safe_div(top1, positive_sum, 0.0) or 0.0
    top3_pos_conc = _safe_div(top3, positive_sum, 0.0) or 0.0
    top5_pos_conc = _safe_div(top5, positive_sum, 0.0) or 0.0
    top1_net_contrib = _safe_div(top1, net_sum, 0.0) if net_sum > 0 else None
    by_exit_reason = _count_by(trades, "exit_reason")
    by_side_counts = _count_by(trades, "side")
    by_regime_counts = _count_by(trades, "regime")
    by_quality_counts = _count_by(trades, "quality_grade")
    by_side: dict[str, dict[str, Any]] = {}
    for side in sorted(set(str(t.get("side", "UNKNOWN")) for t in trades) or {"UNKNOWN"}):
        side_rows = [t for t in trades if str(t.get("side", "UNKNOWN")) == side]
        side_r = [_safe_float(t.get("net_r"), 0.0) for t in side_rows]
        by_side[side] = {
            "closed_trades": len(side_rows),
            "sum_r_post_cost": _round(sum(side_r)),
            "avg_r_post_cost": _round(_avg(side_r) or 0.0),
            "median_r_post_cost": _round(_median(side_r) or 0.0),
            "win_rate": _round(_safe_div(len([r for r in side_r if r > settings.breakeven_r_abs]), len(side_r), 0.0) or 0.0, 6),
        }
    count = len(trades)
    return {
        "closed_trades": count,
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), count, 0.0) or 0.0, 6),
        "loss_rate": _round(_safe_div(len(losses), count, 0.0) or 0.0, 6),
        "breakeven_ratio": _round(_safe_div(len(breakevens), count, 0.0) or 0.0, 6),
        "gross_avg_r": _round(_avg(gross_values) or 0.0),
        "avg_cost_r": _round(_avg(cost_values) or 0.0),
        "avg_r_post_cost": _round(_avg(r_values) or 0.0),
        "median_r_post_cost": _round(_median(r_values) or 0.0),
        "p25_r_post_cost": _round(_percentile(r_values, 0.25) or 0.0),
        "p75_r_post_cost": _round(_percentile(r_values, 0.75) or 0.0),
        "sum_r_post_cost": _round(net_sum),
        "sum_net_pnl": _round(sum(pnl_values)),
        "profit_factor_r": _round(_safe_div(positive_sum, negative_sum, None), 8),
        "max_drawdown_r": _round(_max_drawdown(r_values)),
        "positive_sum_r": _round(positive_sum),
        "negative_sum_abs_r": _round(negative_sum),
        "top_1_trade_r": _round(top1),
        "top_3_trade_r": _round(top3),
        "top_5_trade_r": _round(top5),
        "top_1_positive_concentration": _round(top1_pos_conc),
        "top_3_positive_concentration": _round(top3_pos_conc),
        "top_5_positive_concentration": _round(top5_pos_conc),
        "top_1_net_contribution": _round(top1_net_contrib) if top1_net_contrib is not None else None,
        "top_trade_concentration_ok": bool(top1_pos_conc <= settings.max_top1_positive_concentration or positive_sum <= 0),
        "top3_concentration_ok": bool(top3_pos_conc <= settings.max_top3_positive_concentration or len(positives) < 3 or positive_sum <= 0),
        "top5_concentration_ok": bool(top5_pos_conc <= settings.max_top5_positive_concentration or len(positives) < 5 or positive_sum <= 0),
        "top1_net_contribution_ok": bool(top1_net_contrib is None or top1_net_contrib <= settings.max_top1_net_contribution),
        "by_exit_reason": by_exit_reason,
        "by_side_counts": by_side_counts,
        "by_side": by_side,
        "by_regime_counts": by_regime_counts,
        "by_quality_counts": by_quality_counts,
        "ambiguous_same_bar_hits": len([t for t in trades if t.get("ambiguous_same_bar_hit")]),
        "timeout_trades": by_exit_reason.get("TIME_EXIT", 0),
        "stop_loss_trades": sum(v for k, v in by_exit_reason.items() if "STOP_LOSS" in k),
        "take_profit_trades": by_exit_reason.get("TAKE_PROFIT", 0),
    }


def _build_by_window_report(
    trades: Sequence[dict[str, Any]],
    settings: LSRV2TradeForensicsSettings,
    *,
    report_path: Path,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cost_models = sorted(set(str(t.get("cost_model", "UNKNOWN")) for t in trades))
    windows = sorted(set(_safe_int(t.get("window_size"), 0) for t in trades if _safe_int(t.get("window_size"), 0) > 0))
    for window in windows:
        for cost_model in cost_models:
            subset = [t for t in trades if _safe_int(t.get("window_size"), 0) == window and str(t.get("cost_model")) == cost_model]
            if not subset:
                continue
            summary = _summarize_trades(subset, settings)
            summary.update({
                "window_size": window,
                "window_label": _window_label(window),
                "cost_model": cost_model,
            })
            rows.append(summary)
    primary = [r for r in rows if r.get("cost_model") == settings.primary_cost_model and _safe_int(r.get("window_size"), 0) in set(settings.primary_windows)]
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS",
        "decision": "LSR_V2_FORENSICS_BY_WINDOW_READY_DIAGNOSTIC",
        "created_at": utc_now_iso(),
        "primary_cost_model": settings.primary_cost_model,
        "primary_windows": list(settings.primary_windows),
        "positive_primary_windows": sum(1 for r in primary if _safe_float(r.get("sum_r_post_cost"), 0.0) > 0),
        "negative_primary_windows": sum(1 for r in primary if _safe_float(r.get("sum_r_post_cost"), 0.0) <= 0),
        "window_count": len(rows),
        "rows": rows,
        "orders_submitted_by_lsr_v2_forensics": 0,
        "positions_opened_by_lsr_v2_forensics": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def _build_cost_failure_report(
    trades: Sequence[dict[str, Any]],
    settings: LSRV2TradeForensicsSettings,
    *,
    report_path: Path,
) -> dict[str, Any]:
    primary_rows = [t for t in trades if str(t.get("cost_model")) == settings.primary_cost_model and _safe_int(t.get("window_size"), 0) in set(settings.primary_windows)]
    severe_rows = [t for t in trades if str(t.get("cost_model")) == settings.severe_cost_model and _safe_int(t.get("window_size"), 0) in set(settings.primary_windows)]
    severe_by_key = {_trade_key(t): t for t in severe_rows}
    paired: list[dict[str, Any]] = []
    for p in primary_rows:
        sev = severe_by_key.get(_trade_key(p))
        if not sev:
            continue
        cons_r = _safe_float(p.get("net_r"), 0.0)
        sev_r = _safe_float(sev.get("net_r"), 0.0)
        gross_r = _safe_float(p.get("gross_r"), 0.0)
        cons_cost = _safe_float(p.get("cost_r"), 0.0)
        sev_cost = _safe_float(sev.get("cost_r"), 0.0)
        degradation = sev_r - cons_r
        if cons_r > settings.breakeven_r_abs and sev_r < -settings.breakeven_r_abs:
            bucket = "conservative_win_to_severe_loss"
        elif cons_r > settings.breakeven_r_abs and sev_r <= settings.breakeven_r_abs:
            bucket = "conservative_win_to_severe_non_win"
        elif cons_r > 0 and sev_r <= 0:
            bucket = "conservative_positive_to_severe_nonpositive"
        elif cons_r <= 0 and sev_r <= cons_r:
            bucket = "already_weak_and_worse_under_severe"
        else:
            bucket = "survives_severe_cost"
        paired.append({
            "trade_key": _trade_key(p),
            "candidate_id": p.get("candidate_id"),
            "window_size": p.get("window_size"),
            "window_label": p.get("window_label"),
            "side": p.get("side"),
            "exit_reason": p.get("exit_reason"),
            "entry_timestamp": p.get("entry_timestamp"),
            "exit_timestamp": p.get("exit_timestamp"),
            "gross_r": _round(gross_r),
            "primary_net_r": _round(cons_r),
            "severe_net_r": _round(sev_r),
            "primary_cost_r": _round(cons_cost),
            "severe_cost_r": _round(sev_cost),
            "additional_cost_r": _round(sev_cost - cons_cost),
            "severe_degradation_r": _round(degradation),
            "bucket": bucket,
        })
    by_bucket: dict[str, int] = {}
    total_degradation = 0.0
    severe_positive = 0
    primary_positive = 0
    for row in paired:
        bucket = str(row.get("bucket", "UNKNOWN"))
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
        total_degradation += _safe_float(row.get("severe_degradation_r"), 0.0)
        if _safe_float(row.get("primary_net_r"), 0.0) > 0:
            primary_positive += 1
        if _safe_float(row.get("severe_net_r"), 0.0) > 0:
            severe_positive += 1
    win_to_nonwin = by_bucket.get("conservative_win_to_severe_non_win", 0) + by_bucket.get("conservative_win_to_severe_loss", 0)
    flip_ratio = _safe_div(win_to_nonwin, max(primary_positive, 1), 0.0) or 0.0
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS",
        "decision": "LSR_V2_COST_FAILURE_ATTRIBUTION_READY_DIAGNOSTIC",
        "created_at": utc_now_iso(),
        "primary_cost_model": settings.primary_cost_model,
        "severe_cost_model": settings.severe_cost_model,
        "paired_trade_count": len(paired),
        "primary_positive_trades": primary_positive,
        "severe_positive_trades": severe_positive,
        "positive_trade_survival_ratio": _round(_safe_div(severe_positive, primary_positive, 0.0) or 0.0, 6),
        "win_to_nonwin_under_severe_count": win_to_nonwin,
        "win_to_nonwin_under_severe_ratio": _round(flip_ratio, 6),
        "total_severe_degradation_r": _round(total_degradation),
        "avg_severe_degradation_r": _round(_safe_div(total_degradation, len(paired), 0.0) or 0.0),
        "cost_sensitive_edge": bool(abs(total_degradation) >= settings.severe_degradation_warn_r or flip_ratio >= settings.cost_flip_warn_ratio),
        "by_bucket": dict(sorted(by_bucket.items())),
        "worst_degraded_trades": sorted(paired, key=lambda r: _safe_float(r.get("severe_degradation_r"), 0.0))[:10],
        "orders_submitted_by_lsr_v2_forensics": 0,
        "positions_opened_by_lsr_v2_forensics": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def _classify_edge(
    *,
    primary_summary: dict[str, Any],
    by_window_report: dict[str, Any],
    cost_failure_report: dict[str, Any],
    matrix_report: dict[str, Any],
    settings: LSRV2TradeForensicsSettings,
) -> tuple[list[str], list[str]]:
    classifications: list[str] = []
    blockers: list[str] = []
    closed = _safe_int(primary_summary.get("closed_trades"), 0)
    net_sum = _safe_float(primary_summary.get("sum_r_post_cost"), 0.0)
    avg_r = _safe_float(primary_summary.get("avg_r_post_cost"), 0.0)
    positive_windows = _safe_int(by_window_report.get("positive_primary_windows"), 0)
    top1_bad = not bool(primary_summary.get("top_trade_concentration_ok", False)) or not bool(primary_summary.get("top1_net_contribution_ok", False))
    top3_bad = not bool(primary_summary.get("top3_concentration_ok", False))
    cost_sensitive = bool(cost_failure_report.get("cost_sensitive_edge", False))

    matrix_criteria = matrix_report.get("criteria") if isinstance(matrix_report.get("criteria"), dict) else {}
    matrix_blockers = matrix_criteria.get("blockers") if isinstance(matrix_criteria.get("blockers"), list) else []

    if closed < settings.min_closed_trades:
        classifications.append("LOW_SAMPLE_EDGE")
        blockers.append("closed_trades_below_minimum")
    if positive_windows < settings.min_positive_windows:
        classifications.append("WINDOW_INSTABILITY_EDGE")
        blockers.append("positive_windows_below_threshold")
    if top1_bad or top3_bad:
        classifications.append("OUTLIER_DOMINATED_EDGE")
        blockers.append("top_trade_concentration_not_ok")
    if cost_sensitive or "severe_cost_survival_not_ok" in matrix_blockers:
        classifications.append("COST_SENSITIVE_EDGE")
        blockers.append("severe_cost_survival_not_ok")
    if net_sum <= 0 or avg_r <= 0:
        classifications.append("REJECT_LSR_V2_CURRENT_FORM")
        blockers.append("non_positive_primary_edge")

    # Retain upstream blockers that are not directly recomputed here.
    for blocker in matrix_blockers:
        if blocker not in blockers:
            blockers.append(str(blocker))

    if not classifications:
        classifications.append("RESEARCH_READY_FOR_WALK_FORWARD")
    elif net_sum > 0 and avg_r > 0:
        classifications.insert(0, "FRAGILE_POSITIVE_EDGE")

    # Keep order but remove duplicates.
    classifications = list(dict.fromkeys(classifications))
    blockers = list(dict.fromkeys(blockers))
    return classifications, blockers


def run_lsr_v2_trade_forensics(settings: LSRV2TradeForensicsSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2TradeForensicsSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    forensics_path = data_dir / FORENSICS_REPORT_NAME
    by_window_path = data_dir / BY_WINDOW_REPORT_NAME
    cost_failure_path = data_dir / COST_FAILURE_REPORT_NAME
    matrix_path = data_dir / MATRIX_REPORT_NAME
    cost_stress_path = data_dir / COST_STRESS_REPORT_NAME

    try:
        trades, trade_files, missing_files = _load_trade_files(data_dir, settings)
        matrix_report = _read_json(matrix_path)
        cost_stress_report = _read_json(cost_stress_path)
        if not trades:
            empty_by_window = {
                "prompt_id": PROMPT_ID,
                "status": "WARN",
                "decision": NO_TRADES_DECISION,
                "created_at": utc_now_iso(),
                "rows": [],
                "report": str(by_window_path),
                "promotion_ready": False,
            }
            empty_cost_failure = {
                "prompt_id": PROMPT_ID,
                "status": "WARN",
                "decision": NO_TRADES_DECISION,
                "created_at": utc_now_iso(),
                "paired_trade_count": 0,
                "report": str(cost_failure_path),
                "promotion_ready": False,
            }
            _write_json(by_window_path, empty_by_window)
            _write_json(cost_failure_path, empty_cost_failure)
            report = {
                "prompt_id": PROMPT_ID,
                "status": "WARN",
                "decision": NO_TRADES_DECISION,
                "created_at": utc_now_iso(),
                "data_dir": str(data_dir),
                "trade_files": trade_files,
                "missing_trade_files": missing_files,
                "trades_loaded": 0,
                "primary_closed_trades": 0,
                "classification_labels": ["LOW_SAMPLE_EDGE"],
                "blockers": ["no_trade_files_or_no_trade_rows"],
                "orders_submitted_by_lsr_v2_forensics": 0,
                "positions_opened_by_lsr_v2_forensics": 0,
                "live_allowed": False,
                "testnet_allowed": False,
                "exchange_broker_allowed": False,
                "audit_only": True,
                "promotion_ready": False,
                "report": str(forensics_path),
                "by_window_report": str(by_window_path),
                "cost_failure_report": str(cost_failure_path),
            }
            _write_json(forensics_path, report)
            return report

        primary_trades = [
            t for t in trades
            if str(t.get("cost_model")) == settings.primary_cost_model
            and _safe_int(t.get("window_size"), 0) in set(settings.primary_windows)
        ]
        all_primary_summary = _summarize_trades(primary_trades, settings)
        all_trades_summary = _summarize_trades(trades, settings)
        by_window_report = _build_by_window_report(trades, settings, report_path=by_window_path)
        cost_failure_report = _build_cost_failure_report(trades, settings, report_path=cost_failure_path)
        classifications, blockers = _classify_edge(
            primary_summary=all_primary_summary,
            by_window_report=by_window_report,
            cost_failure_report=cost_failure_report,
            matrix_report=matrix_report,
            settings=settings,
        )
        if "RESEARCH_READY_FOR_WALK_FORWARD" in classifications:
            decision = READY_DECISION
        else:
            decision = FRAGILE_DECISION
        status = "PASS"
        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
            "created_at": utc_now_iso(),
            "data_dir": str(data_dir),
            "settings": asdict(settings),
            "trade_files": trade_files,
            "missing_trade_files": missing_files,
            "matrix_report_loaded": bool(matrix_report),
            "cost_stress_report_loaded": bool(cost_stress_report),
            "upstream_matrix_decision": matrix_report.get("decision"),
            "upstream_matrix_blockers": (matrix_report.get("criteria") or {}).get("blockers", []) if isinstance(matrix_report.get("criteria"), dict) else [],
            "trades_loaded": len(trades),
            "primary_cost_model": settings.primary_cost_model,
            "primary_windows": list(settings.primary_windows),
            "primary_closed_trades": all_primary_summary.get("closed_trades", 0),
            "primary_summary": all_primary_summary,
            "all_cost_models_summary": all_trades_summary,
            "positive_primary_windows": by_window_report.get("positive_primary_windows", 0),
            "classification_labels": classifications,
            "blockers": blockers,
            "edge_state": classifications[0] if classifications else "UNKNOWN",
            "forensic_note": "diagnostic attribution only; positive conservative backtest is not promotion without walk-forward/OOS/bootstrap and promotion gate",
            "orders_submitted_by_lsr_v2_forensics": 0,
            "positions_opened_by_lsr_v2_forensics": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "broker_submit_called": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "requires LSR-v2 research readiness plus walk-forward, embargoed OOS, bootstrap and strategy promotion gate",
            "report": str(forensics_path),
            "by_window_report": str(by_window_path),
            "cost_failure_report": str(cost_failure_path),
        }
        _write_json(forensics_path, report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": LOAD_ERROR_DECISION,
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "orders_submitted_by_lsr_v2_forensics": 0,
            "positions_opened_by_lsr_v2_forensics": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(forensics_path),
            "by_window_report": str(by_window_path),
            "cost_failure_report": str(cost_failure_path),
        }
        _write_json(forensics_path, report)
        return report
