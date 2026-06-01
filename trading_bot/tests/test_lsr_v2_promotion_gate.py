from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_promotion_gate import (
    BLOCKED_DECISION,
    INCOMPLETE_DECISION,
    PASS_DECISION,
    REJECT_DECISION,
    LSRV2PromotionGateSettings,
    run_lsr_v2_promotion_gate,
)
from trading_bot.core.lsr_v2_selected_overlay_validation import SELECTED_OVERLAY_ID
from trading_bot.core.lsr_v2_combined_risk_overlay import LOCKED_PROFILE_NAME, LOCKED_VARIANT_ID


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_required_reports(data_dir: Path, *, selected_overrides: dict | None = None, combined_overrides: dict | None = None, sample_overrides: dict | None = None) -> None:
    selected = {
        "status": "PASS",
        "decision": "LSR_V2_SELECTED_OVERLAY_READY_FOR_PROMOTION_GATE",
        "classification_labels": ["SELECTED_OVERLAY_VALIDATION_PASS", "READY_FOR_PROMOTION_GATE_REVIEW"],
        "blockers": [],
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "selected_overlay_id": SELECTED_OVERLAY_ID,
        "overlay_oracle": False,
        "selected_primary_trades": 425,
        "primary_avg_r_post_cost": 0.59432544,
        "primary_sum_r_post_cost": 252.58831065,
        "primary_max_drawdown_r": 14.79317364,
        "max_consecutive_losses": 8,
        "walk_forward_stable": True,
        "walk_forward_positive_ratio": 0.875,
        "oos_pass": True,
        "oos_avg_r_post_cost": 0.71290655,
        "oos_sum_r_post_cost": 60.59705685,
        "bootstrap_pass": True,
        "bootstrap_positive_ratio": 1.0,
        "bootstrap_median_avg_r": 0.59443549,
        "cost_degradation_non_destructive": True,
        "cost_degradation_ratio": 0.81739556,
        "severe_positive_ratio": 0.64705882,
        "asset_stability_ok": True,
        "timeframe_stability_ok": True,
        "side_stability_ok": True,
        "orders_submitted_by_lsr_v2_selected_overlay_validation": 0,
        "positions_opened_by_lsr_v2_selected_overlay_validation": 0,
        "promotion_ready": False,
    }
    if selected_overrides:
        selected.update(selected_overrides)

    combined = {
        "status": "PASS",
        "decision": "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS",
        "best_combined_overlay_id": SELECTED_OVERLAY_ID,
        "best_combined_overlay_valid": True,
        "orders_submitted_by_lsr_v2_combined_overlay": 0,
        "positions_opened_by_lsr_v2_combined_overlay": 0,
        "promotion_ready": False,
    }
    if combined_overrides:
        combined.update(combined_overrides)

    sample = {
        "status": "PASS",
        "decision": "LSR_V2_SAMPLE_EXPANSION_READY_FOR_WALK_FORWARD",
        "closed_trades": 1695,
        "orders_submitted_by_lsr_v2_sample_expansion": 0,
        "positions_opened_by_lsr_v2_sample_expansion": 0,
        "promotion_ready": False,
    }
    if sample_overrides:
        sample.update(sample_overrides)

    _write_json(data_dir / "lsr_v2_selected_overlay_validation_report.json", selected)
    _write_json(data_dir / "lsr_v2_selected_overlay_walk_forward_report.json", {"status": "PASS", "walk_forward_stable": True})
    _write_json(data_dir / "lsr_v2_selected_overlay_oos_report.json", {"status": "PASS", "oos_pass": True})
    _write_json(data_dir / "lsr_v2_selected_overlay_bootstrap_report.json", {"status": "PASS", "bootstrap_pass": True})
    _write_json(data_dir / "lsr_v2_combined_risk_overlay_report.json", combined)
    _write_json(data_dir / "lsr_v2_operational_viability_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS"})
    _write_json(data_dir / "lsr_v2_sample_expansion_report.json", sample)


def test_missing_reports_are_incomplete_and_safe(tmp_path: Path) -> None:
    report = run_lsr_v2_promotion_gate(LSRV2PromotionGateSettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == INCOMPLETE_DECISION
    assert report["paper_supervised_candidate"] is False
    assert report["orders_submitted_by_lsr_v2_promotion_gate"] == 0
    assert report["positions_opened_by_lsr_v2_promotion_gate"] == 0
    assert report["broker_submit_called"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False
    assert (tmp_path / "lsr_v2_promotion_gate_report.json").exists()


def test_promotion_gate_passes_with_selected_overlay_validation(tmp_path: Path) -> None:
    _write_required_reports(tmp_path)
    report = run_lsr_v2_promotion_gate(LSRV2PromotionGateSettings(data_dir=str(tmp_path)))
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["paper_supervised_candidate"] is True
    assert report["paper_supervised_readiness_preflight_pass"] is True
    assert report["promotion_ready"] is False
    assert report["execution_enabled"] is False
    assert report["routing_enabled"] is False
    assert report["paper_order_submission_enabled"] is False
    assert report["orders_submitted_by_lsr_v2_promotion_gate"] == 0
    assert report["positions_opened_by_lsr_v2_promotion_gate"] == 0
    assert report["broker_submit_called"] is False


def test_promotion_gate_blocks_if_metric_fails(tmp_path: Path) -> None:
    _write_required_reports(tmp_path, selected_overrides={"primary_max_drawdown_r": 15.01})
    report = run_lsr_v2_promotion_gate(LSRV2PromotionGateSettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == BLOCKED_DECISION
    assert "primary_max_drawdown_above_limit" in report["blockers"]
    assert report["paper_supervised_candidate"] is False


def test_promotion_gate_blocks_oracle_overlay(tmp_path: Path) -> None:
    _write_required_reports(tmp_path, selected_overrides={"overlay_oracle": True})
    report = run_lsr_v2_promotion_gate(LSRV2PromotionGateSettings(data_dir=str(tmp_path)))
    assert report["decision"] == BLOCKED_DECISION
    assert "selected_overlay_is_oracle" in report["blockers"]
    assert report["paper_supervised_candidate"] is False


def test_promotion_gate_rejects_input_safety_leakage(tmp_path: Path) -> None:
    _write_required_reports(tmp_path, selected_overrides={"orders_submitted_by_lsr_v2_selected_overlay_validation": 1})
    report = run_lsr_v2_promotion_gate(LSRV2PromotionGateSettings(data_dir=str(tmp_path)))
    assert report["decision"] == REJECT_DECISION
    assert any(b.startswith("safety_violation") for b in report["blockers"])
    assert report["paper_supervised_candidate"] is False
    assert report["orders_submitted_by_lsr_v2_promotion_gate"] == 0
    assert report["positions_opened_by_lsr_v2_promotion_gate"] == 0
