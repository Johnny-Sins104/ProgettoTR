"""Prompt 29.4.4s-9 — LSR-v2 promotion gate / paper-supervised readiness preflight.

This module is a diagnostic-only gate for the locked LSR-v2 research profile:

* strategy profile: LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24
* execution: retest_entry_limit_like + stop_at_sweep_extreme + tp_fixed_2R + hold_24
* selected risk overlay: combo_loss3_dd10_side_cap

The gate reads the reports produced by the previous diagnostic stages and emits a
single paper-supervised-candidate decision. It must not route signals, submit
orders, open positions, call a broker, mutate paper state, enable live/testnet,
or set operational execution flags.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json

try:  # keep tests independent from full project imports when needed
    from .lsr_v2_combined_risk_overlay import LOCKED_PROFILE_NAME, LOCKED_VARIANT_ID
    from .lsr_v2_selected_overlay_validation import SELECTED_OVERLAY_ID
except Exception:  # pragma: no cover - defensive fallback for stripped contexts
    LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"
    SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

PROMPT_ID = "29.4.4s-9"
REPORT_NAME = "lsr_v2_promotion_gate_report.json"

SELECTED_VALIDATION_REPORT_NAME = "lsr_v2_selected_overlay_validation_report.json"
SELECTED_WALK_FORWARD_REPORT_NAME = "lsr_v2_selected_overlay_walk_forward_report.json"
SELECTED_OOS_REPORT_NAME = "lsr_v2_selected_overlay_oos_report.json"
SELECTED_BOOTSTRAP_REPORT_NAME = "lsr_v2_selected_overlay_bootstrap_report.json"
COMBINED_OVERLAY_REPORT_NAME = "lsr_v2_combined_risk_overlay_report.json"
OPERATIONAL_PREFLIGHT_REPORT_NAME = "lsr_v2_operational_viability_preflight_report.json"
SAMPLE_EXPANSION_REPORT_NAME = "lsr_v2_sample_expansion_report.json"

PASS_DECISION = "LSR_V2_PAPER_SUPERVISED_CANDIDATE"
BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_BLOCKED"
INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_REPORTS_INCOMPLETE"
REJECT_DECISION = "REJECT_LSR_V2_PROMOTION_GATE_FAILED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_GATE_ERROR"

REQUIRED_REPORTS = {
    "selected_overlay_validation": SELECTED_VALIDATION_REPORT_NAME,
    "selected_overlay_walk_forward": SELECTED_WALK_FORWARD_REPORT_NAME,
    "selected_overlay_oos": SELECTED_OOS_REPORT_NAME,
    "selected_overlay_bootstrap": SELECTED_BOOTSTRAP_REPORT_NAME,
    "combined_risk_overlay": COMBINED_OVERLAY_REPORT_NAME,
    "operational_viability_preflight": OPERATIONAL_PREFLIGHT_REPORT_NAME,
    "sample_expansion": SAMPLE_EXPANSION_REPORT_NAME,
}


@dataclass(frozen=True)
class LSRV2PromotionGateSettings:
    data_dir: str = "data"
    selected_validation_report_path: str | None = None
    walk_forward_report_path: str | None = None
    oos_report_path: str | None = None
    bootstrap_report_path: str | None = None
    combined_overlay_report_path: str | None = None
    operational_preflight_report_path: str | None = None
    sample_expansion_report_path: str | None = None
    min_selected_primary_trades: int = 300
    min_primary_avg_r: float = 0.0
    min_primary_sum_r: float = 0.0
    max_primary_drawdown_r: float = 15.0
    max_consecutive_losses: int = 10
    min_walk_forward_positive_ratio: float = 0.55
    min_oos_avg_r: float = 0.0
    min_bootstrap_positive_ratio: float = 0.60
    max_cost_degradation_ratio: float = 1.25
    min_severe_positive_ratio: float = 0.60
    min_sample_expansion_trades: int = 300
    require_no_input_blockers: bool = True

    @classmethod
    def default(cls) -> "LSRV2PromotionGateSettings":
        return cls()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: Any, digits: int = 8) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw) if raw.strip() else {}
        return parsed if isinstance(parsed, dict) else {"_non_object_json": parsed}
    except Exception as exc:
        return {"_read_error": str(exc)}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _path_for(settings: LSRV2PromotionGateSettings, key: str, filename: str) -> Path:
    override = {
        "selected_overlay_validation": settings.selected_validation_report_path,
        "selected_overlay_walk_forward": settings.walk_forward_report_path,
        "selected_overlay_oos": settings.oos_report_path,
        "selected_overlay_bootstrap": settings.bootstrap_report_path,
        "combined_risk_overlay": settings.combined_overlay_report_path,
        "operational_viability_preflight": settings.operational_preflight_report_path,
        "sample_expansion": settings.sample_expansion_report_path,
    }.get(key)
    return Path(override) if override else Path(settings.data_dir) / filename


def _load_reports(settings: LSRV2PromotionGateSettings) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    reports: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    blockers: list[str] = []
    for key, filename in REQUIRED_REPORTS.items():
        path = _path_for(settings, key, filename)
        paths[key] = str(path)
        payload = _read_json(path)
        if payload is None:
            blockers.append(f"missing_report:{filename}")
            reports[key] = {}
            continue
        if "_read_error" in payload:
            blockers.append(f"unreadable_report:{filename}")
        reports[key] = payload
    return reports, paths, blockers


def _iter_items(obj: Any, prefix: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key, value
            yield from _iter_items(value, path)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            path = f"{prefix}[{idx}]"
            yield from _iter_items(value, path)


def _input_safety_blockers(reports: Mapping[str, Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    numeric_forbidden = (
        "orders_submitted",
        "positions_opened",
        "broker_submit_called_count",
        "broker_submit_called",
    )
    boolean_forbidden = (
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "broker_submit_called",
        "would_submit_to_paper_broker",
    )
    for report_name, report in reports.items():
        for path, key, value in _iter_items(report):
            key_l = str(key).lower()
            if any(token in key_l for token in numeric_forbidden):
                if isinstance(value, bool):
                    if value:
                        blockers.append(f"safety_violation:{report_name}:{path}=true")
                elif _safe_float(value, 0.0) != 0.0:
                    blockers.append(f"safety_violation:{report_name}:{path}={value}")
            if any(token == key_l for token in boolean_forbidden):
                if _safe_bool(value, False):
                    blockers.append(f"safety_violation:{report_name}:{path}=true")
    return sorted(set(blockers))


def _metric_checks(settings: LSRV2PromotionGateSettings, reports: Mapping[str, Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    labels: list[str] = []
    selected = dict(reports.get("selected_overlay_validation") or {})
    combined = dict(reports.get("combined_risk_overlay") or {})
    sample = dict(reports.get("sample_expansion") or {})

    if selected.get("status") != "PASS":
        blockers.append("selected_overlay_validation_status_not_pass")
    if selected.get("decision") != "LSR_V2_SELECTED_OVERLAY_READY_FOR_PROMOTION_GATE":
        blockers.append("selected_overlay_not_ready_for_promotion_gate")
    if selected.get("locked_profile_name") != LOCKED_PROFILE_NAME:
        blockers.append("locked_profile_mismatch")
    if selected.get("locked_variant_id") != LOCKED_VARIANT_ID:
        blockers.append("locked_variant_mismatch")
    if selected.get("selected_overlay_id") != SELECTED_OVERLAY_ID:
        blockers.append("selected_overlay_mismatch")
    if _safe_bool(selected.get("overlay_oracle"), True):
        blockers.append("selected_overlay_is_oracle")

    selected_input_blockers = selected.get("blockers") or []
    if settings.require_no_input_blockers and selected_input_blockers:
        blockers.append("selected_overlay_validation_has_blockers")

    selected_primary_trades = _safe_int(selected.get("selected_primary_trades"), 0)
    if selected_primary_trades < settings.min_selected_primary_trades:
        blockers.append("selected_primary_trades_below_minimum")
    if _safe_float(selected.get("primary_avg_r_post_cost"), 0.0) <= settings.min_primary_avg_r:
        blockers.append("primary_avg_r_not_positive")
    if _safe_float(selected.get("primary_sum_r_post_cost"), 0.0) <= settings.min_primary_sum_r:
        blockers.append("primary_sum_r_not_positive")
    if _safe_float(selected.get("primary_max_drawdown_r"), 1e9) > settings.max_primary_drawdown_r:
        blockers.append("primary_max_drawdown_above_limit")
    if _safe_int(selected.get("max_consecutive_losses"), 1_000_000) > settings.max_consecutive_losses:
        blockers.append("max_consecutive_losses_above_limit")

    if not _safe_bool(selected.get("walk_forward_stable"), False):
        blockers.append("walk_forward_not_stable")
    if _safe_float(selected.get("walk_forward_positive_ratio"), 0.0) < settings.min_walk_forward_positive_ratio:
        blockers.append("walk_forward_positive_ratio_below_minimum")
    if not _safe_bool(selected.get("oos_pass"), False):
        blockers.append("oos_not_pass")
    if _safe_float(selected.get("oos_avg_r_post_cost"), 0.0) <= settings.min_oos_avg_r:
        blockers.append("oos_avg_r_not_positive")
    if _safe_float(selected.get("oos_sum_r_post_cost"), 0.0) <= 0.0:
        blockers.append("oos_sum_r_not_positive")
    if not _safe_bool(selected.get("bootstrap_pass"), False):
        blockers.append("bootstrap_not_pass")
    if _safe_float(selected.get("bootstrap_positive_ratio"), 0.0) < settings.min_bootstrap_positive_ratio:
        blockers.append("bootstrap_positive_ratio_below_minimum")
    if _safe_float(selected.get("bootstrap_median_avg_r"), 0.0) <= 0.0:
        blockers.append("bootstrap_median_avg_r_not_positive")
    if not _safe_bool(selected.get("cost_degradation_non_destructive"), False):
        blockers.append("cost_degradation_destructive")
    if _safe_float(selected.get("cost_degradation_ratio"), 1e9) > settings.max_cost_degradation_ratio:
        blockers.append("cost_degradation_ratio_above_limit")
    if _safe_float(selected.get("severe_positive_ratio"), 0.0) < settings.min_severe_positive_ratio:
        blockers.append("severe_positive_ratio_below_minimum")
    if not _safe_bool(selected.get("asset_stability_ok"), False):
        blockers.append("asset_stability_not_ok")
    if not _safe_bool(selected.get("timeframe_stability_ok"), False):
        blockers.append("timeframe_stability_not_ok")
    if not _safe_bool(selected.get("side_stability_ok"), False):
        blockers.append("side_stability_not_ok")

    if combined:
        if combined.get("status") != "PASS":
            blockers.append("combined_overlay_status_not_pass")
        if combined.get("decision") != "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS":
            blockers.append("combined_overlay_preflight_not_pass")
        if not _safe_bool(combined.get("best_combined_overlay_valid"), False):
            blockers.append("combined_overlay_not_valid")
        if combined.get("best_combined_overlay_id") != SELECTED_OVERLAY_ID:
            blockers.append("combined_overlay_id_mismatch")
    if sample:
        if sample.get("status") != "PASS":
            blockers.append("sample_expansion_status_not_pass")
        if sample.get("decision") != "LSR_V2_SAMPLE_EXPANSION_READY_FOR_WALK_FORWARD":
            blockers.append("sample_expansion_not_ready_for_walk_forward")
        if _safe_int(sample.get("closed_trades"), 0) < settings.min_sample_expansion_trades:
            blockers.append("sample_expansion_trades_below_minimum")

    if not blockers:
        labels.extend([
            "PROMOTION_GATE_PASS",
            "PAPER_SUPERVISED_CANDIDATE_READY",
            "EXECUTION_STILL_DISABLED",
        ])
    else:
        if any(b.startswith("safety_violation") for b in blockers):
            labels.append("SAFETY_INVARIANT_FAILED")
        if any("missing_report" in b or "unreadable_report" in b for b in blockers):
            labels.append("REPORTS_INCOMPLETE")
        labels.append("PROMOTION_BLOCKED")
    return sorted(set(blockers)), labels


def _decision_for(blockers: list[str], missing_blockers: list[str]) -> str:
    if missing_blockers:
        return INCOMPLETE_DECISION
    if not blockers:
        return PASS_DECISION
    if any(b.startswith("safety_violation") for b in blockers):
        return REJECT_DECISION
    return BLOCKED_DECISION


def run_lsr_v2_promotion_gate(settings: LSRV2PromotionGateSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2PromotionGateSettings.default()
    data_dir = Path(settings.data_dir)
    report_path = data_dir / REPORT_NAME

    try:
        reports, report_paths, load_blockers = _load_reports(settings)
        safety_blockers = _input_safety_blockers(reports)
        if load_blockers:
            metric_blockers = []
            labels = ["REPORTS_INCOMPLETE", "PROMOTION_BLOCKED"]
        else:
            metric_blockers, labels = _metric_checks(settings, reports)
        blockers = sorted(set(load_blockers + safety_blockers + metric_blockers))
        decision = _decision_for(blockers, load_blockers)
        status = "PASS" if decision == PASS_DECISION else "WARN"
        paper_supervised_candidate = decision == PASS_DECISION

        selected = reports.get("selected_overlay_validation") or {}
        combined = reports.get("combined_risk_overlay") or {}
        sample = reports.get("sample_expansion") or {}

        report: dict[str, Any] = {
            "prompt_id": PROMPT_ID,
            "generated_at": utc_now_iso(),
            "status": status,
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "locked_profile_name": selected.get("locked_profile_name") or LOCKED_PROFILE_NAME,
            "locked_variant_id": selected.get("locked_variant_id") or LOCKED_VARIANT_ID,
            "selected_overlay_id": selected.get("selected_overlay_id") or SELECTED_OVERLAY_ID,
            "overlay_oracle": _safe_bool(selected.get("overlay_oracle"), True),
            "paper_supervised_candidate": paper_supervised_candidate,
            "paper_supervised_readiness_preflight_pass": paper_supervised_candidate,
            "promotion_ready": False,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_called": False,
            "orders_submitted_by_lsr_v2_promotion_gate": 0,
            "positions_opened_by_lsr_v2_promotion_gate": 0,
            "audit_only": True,
            "selected_primary_trades": _safe_int(selected.get("selected_primary_trades"), 0),
            "primary_avg_r_post_cost": _round(selected.get("primary_avg_r_post_cost")),
            "primary_sum_r_post_cost": _round(selected.get("primary_sum_r_post_cost")),
            "primary_max_drawdown_r": _round(selected.get("primary_max_drawdown_r")),
            "max_consecutive_losses": _safe_int(selected.get("max_consecutive_losses"), 0),
            "walk_forward_stable": _safe_bool(selected.get("walk_forward_stable"), False),
            "walk_forward_positive_ratio": _round(selected.get("walk_forward_positive_ratio")),
            "oos_pass": _safe_bool(selected.get("oos_pass"), False),
            "oos_avg_r_post_cost": _round(selected.get("oos_avg_r_post_cost")),
            "oos_sum_r_post_cost": _round(selected.get("oos_sum_r_post_cost")),
            "bootstrap_pass": _safe_bool(selected.get("bootstrap_pass"), False),
            "bootstrap_positive_ratio": _round(selected.get("bootstrap_positive_ratio")),
            "bootstrap_median_avg_r": _round(selected.get("bootstrap_median_avg_r")),
            "cost_degradation_non_destructive": _safe_bool(selected.get("cost_degradation_non_destructive"), False),
            "cost_degradation_ratio": _round(selected.get("cost_degradation_ratio")),
            "severe_positive_ratio": _round(selected.get("severe_positive_ratio")),
            "asset_stability_ok": _safe_bool(selected.get("asset_stability_ok"), False),
            "timeframe_stability_ok": _safe_bool(selected.get("timeframe_stability_ok"), False),
            "side_stability_ok": _safe_bool(selected.get("side_stability_ok"), False),
            "combined_overlay_decision": combined.get("decision"),
            "combined_overlay_valid": _safe_bool(combined.get("best_combined_overlay_valid"), False),
            "sample_expansion_decision": sample.get("decision"),
            "sample_expansion_closed_trades": _safe_int(sample.get("closed_trades"), 0),
            "required_report_paths": report_paths,
            "report": str(report_path),
            "settings": asdict(settings),
        }
        _write_json(report_path, report)
        return report
    except Exception as exc:  # pragma: no cover - final defensive safety net
        report = {
            "prompt_id": PROMPT_ID,
            "generated_at": utc_now_iso(),
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": ["PROMOTION_GATE_ERROR"],
            "blockers": [f"promotion_gate_error:{type(exc).__name__}:{exc}"],
            "paper_supervised_candidate": False,
            "paper_supervised_readiness_preflight_pass": False,
            "promotion_ready": False,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_called": False,
            "orders_submitted_by_lsr_v2_promotion_gate": 0,
            "positions_opened_by_lsr_v2_promotion_gate": 0,
            "audit_only": True,
            "report": str(report_path),
        }
        _write_json(report_path, report)
        return report
