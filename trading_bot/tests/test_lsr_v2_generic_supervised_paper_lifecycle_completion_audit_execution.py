from __future__ import annotations

import os
from pathlib import Path

from trading_bot.core.lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution import (
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_lifecycle_completion_audit_execution,
)

REQUIRED = [
    "symbol",
    "side",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_amount",
    "position_size",
    "max_open_positions",
    "paper_only",
]


def _write_json(path: Path, payload: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dry_run_payload() -> dict:
    return {
        "symbol": "deferred_until_explicit_order_intent_patch",
        "side": "deferred_until_explicit_order_intent_patch",
        "entry_price": "deferred_until_explicit_order_intent_patch",
        "stop_loss": "deferred_until_explicit_order_intent_patch",
        "take_profit": "deferred_until_explicit_order_intent_patch",
        "risk_amount": "deferred_until_explicit_order_intent_patch",
        "position_size": "deferred_until_explicit_order_intent_patch",
        "max_open_positions": 1,
        "paper_only": True,
        "runtime_values_present": False,
        "dry_run_only": True,
        "materialized": False,
        "persisted": False,
    }


def _write_markers(tmp_path: Path) -> None:
    paths = {
        "trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold.py": (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_SCAFFOLD\n"
            "generic_lifecycle_completion_audit_execution_scaffold_ready\n"
        ),
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "import argparse\n",
    }
    for rel, text in paths.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _u42_report() -> dict:
    scaffold_map = {
        "dry_run_order_intent_payload": _dry_run_payload(),
        "lifecycle_completion_audit_execution_scaffold_patch": True,
        "lifecycle_completion_audit_execution_scaffold_gate_model": {
            "lifecycle_completion_audit_execution_scaffold_model_ready": True,
            "lifecycle_completion_audit_execution_scaffold_gate_model_ready": True,
            "future_lifecycle_completion_audit_execution_conditions_satisfied": False,
            "lifecycle_completion_audit_execution_allowed": False,
            "postmortem_runtime_executed": False,
            "final_audit_runtime_executed": False,
            "broker_submit_receipt_available": False,
            "broker_close_receipt_available": False,
            "realized_pnl_written": False,
            "lifecycle_state_complete": False,
            "runtime_values_present": False,
        },
    }
    report = {
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_SCAFFOLD_READY",
        "generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_ready": True,
        "generic_lifecycle_completion_audit_execution_scaffold_ready": True,
        "generic_lifecycle_completion_audit_execution_scaffold_model_ready": True,
        "generic_lifecycle_completion_audit_execution_scaffold_patch_ready": True,
        "paper_lifecycle_completion_audit_execution_scaffold_ready": True,
        "lifecycle_completion_audit_execution_scaffold_diagnostic_available": True,
        "lifecycle_completion_audit_execution_scaffold_diagnostic_count": 401,
        "lifecycle_completion_audit_execution_scaffold_contract_present_fields": REQUIRED,
        "lifecycle_completion_audit_execution_scaffold_contract_required_fields": REQUIRED,
        "lifecycle_completion_audit_execution_scaffold_contract_missing_fields": [],
        "generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_map": scaffold_map,
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400, "strategy_signal_diagnostic_read": 1},
        "candidate_diagnostic_examples": [{"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY"}],
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "real_close_execution_available": False,
        "paper_position_closed": False,
        "paper_realized_pnl_reconciliation_ready": False,
        "realized_pnl_written": False,
        "paper_final_audit_ready": False,
        "paper_postmortem_ready": False,
        "paper_lifecycle_completion_ready": False,
        "final_audit_runtime_executed": False,
        "postmortem_runtime_executed": False,
        "generic_lifecycle_completion_audit_allowed": False,
        "generic_lifecycle_completion_audit_execution_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "would_run_lifecycle_completion_audit": False,
        "would_run_postmortem": False,
        "would_run_final_audit": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_submit": False,
        "would_close": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": False,
        "generic_realized_pnl_operator_gate_required": True,
        "generic_realized_pnl_operator_gate_satisfied": False,
        "generic_final_audit_operator_gate_required": True,
        "generic_final_audit_operator_gate_satisfied": False,
        "generic_postmortem_operator_gate_required": True,
        "generic_postmortem_operator_gate_satisfied": False,
        "generic_lifecycle_completion_operator_gate_required": True,
        "generic_lifecycle_completion_operator_gate_satisfied": False,
        "lifecycle_state": "FLAT_LOCKED",
        "lifecycle_state_complete": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "paper_state_status_consistency": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    }
    false_keys = [
        "generic_candidate_detection_allowed",
        "generic_candidate_scan_execution_allowed",
        "generic_candidate_probe_allowed",
        "generic_route_candidate_creation_allowed",
        "generic_route_execution_allowed",
        "generic_handoff_candidate_creation_allowed",
        "generic_handoff_execution_allowed",
        "generic_order_intent_candidate_materialization_allowed",
        "generic_order_intent_validation_allowed",
        "generic_order_intent_validation_execution_allowed",
        "generic_order_intent_materialization_allowed",
        "generic_order_intent_creation_allowed",
        "generic_order_intent_dry_run_execution_allowed",
        "generic_order_intent_activation_allowed",
        "generic_order_intent_activation_execution_allowed",
        "generic_order_intent_persistence_allowed",
        "generic_submit_readiness_preflight_allowed",
        "generic_submit_candidate_audit_allowed",
        "generic_submit_candidate_creation_allowed",
        "generic_submit_execution_allowed",
        "generic_open_position_monitor_allowed",
        "generic_close_execution_allowed",
        "generic_realized_pnl_reconciliation_allowed",
        "paper_engine_mutation_allowed",
        "runner_mutation_allowed",
        "launcher_mutation_allowed",
        "paper_only_execution_allowed",
        "future_integrated_operation_allowed",
    ]
    for key in false_keys:
        report[key] = False
    return report


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir="data")


def test_lifecycle_completion_execution_scaffold_ready_but_runtime_completion_blocked(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_report.json", _u42_report())

    report = run_generic_supervised_paper_lifecycle_completion_audit_execution(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_lifecycle_completion_audit_execution_ready"] is True
    assert report["generic_lifecycle_completion_audit_execution_ready"] is True
    assert report["generic_lifecycle_completion_audit_execution_model_ready"] is True
    assert report["generic_lifecycle_completion_audit_execution_patch_ready"] is True
    assert report["paper_lifecycle_completion_audit_execution_ready"] is True
    assert report["lifecycle_completion_audit_execution_diagnostic_available"] is True
    assert report["lifecycle_completion_audit_execution_diagnostic_count"] == 401
    assert report["lifecycle_completion_audit_execution_contract_shape_modelable"] is True
    assert report["lifecycle_completion_audit_execution_contract_missing_fields"] == []
    assert report["generic_lifecycle_completion_audit_allowed"] is False
    assert report["generic_lifecycle_completion_audit_execution_allowed"] is False
    assert report["paper_lifecycle_completion_ready"] is False
    assert report["would_run_lifecycle_completion_audit"] is False
    assert report["would_mutate_paper_state"] is False
    assert report["would_send_telegram"] is False
    assert report["orders_submitted_by_generic_lifecycle_completion_audit_execution"] == 0
    assert report["positions_closed_by_generic_lifecycle_completion_audit_execution"] == 0
    assert report["paper_state_modified_by_generic_lifecycle_completion_audit_execution"] is False
    lifecycle_completion_map = report["generic_supervised_paper_lifecycle_completion_audit_execution_map"]
    assert lifecycle_completion_map["lifecycle_completion_audit_execution_patch"] is True
    assert lifecycle_completion_map["mode"] == "generic_supervised_paper_lifecycle_completion_audit_execution_controlled"
    gate = lifecycle_completion_map["lifecycle_completion_audit_execution_gate_model"]
    assert gate["lifecycle_completion_audit_execution_model_ready"] is True
    assert gate["lifecycle_completion_audit_execution_allowed"] is False
    assert "postmortem_runtime_execution_absent" in gate["lifecycle_completion_audit_execution_blocked_reasons"]
    

def test_lifecycle_completion_execution_scaffold_requires_upstream_preflight_report(tmp_path):
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_lifecycle_completion_audit_execution(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "missing_upstream_reports" in report["blockers"]
    assert report["generic_supervised_paper_lifecycle_completion_audit_execution_ready"] is False
    assert report["lifecycle_completion_audit_execution_diagnostic_available"] is False
    assert report["generic_lifecycle_completion_audit_execution_allowed"] is False
    assert report["would_run_lifecycle_completion_audit"] is False


def test_lifecycle_completion_execution_scaffold_rejects_not_ready_upstream_report(tmp_path):
    _write_markers(tmp_path)
    upstream = _u42_report()
    upstream["decision"] = "NOT_READY"
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_report.json", upstream)

    report = run_generic_supervised_paper_lifecycle_completion_audit_execution(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "not_ready_upstream_reports" in report["blockers"]
    assert report["generic_lifecycle_completion_audit_execution_allowed"] is False


def test_lifecycle_completion_execution_scaffold_requires_source_markers(tmp_path):
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_report.json", _u42_report())

    report = run_generic_supervised_paper_lifecycle_completion_audit_execution(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "missing_source_markers" in report["blockers"]
    assert report["source_markers_present"] is False
    assert report["generic_lifecycle_completion_audit_execution_allowed"] is False


def test_lifecycle_completion_execution_operator_env_cannot_override_missing_runtime_evidence(tmp_path, monkeypatch):
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold_report.json", _u42_report())
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_CONFIRMATION", "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_MAX_POSITIONS", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_SUBMIT_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_SUBMIT_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_SUBMIT_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_CLOSE_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_CLOSE_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_CLOSE_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_REALIZED_PNL_RECONCILIATION_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_FINAL_AUDIT_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_FINAL_AUDIT_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_FINAL_AUDIT_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_POSTMORTEM_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_POSTMORTEM_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_POSTMORTEM_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_CONFIRMATION", "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_COMPLETION_AUDIT_ONLY")

    report = run_generic_supervised_paper_lifecycle_completion_audit_execution(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["generic_lifecycle_completion_operator_gate_satisfied"] is True
    assert report["generic_postmortem_operator_gate_satisfied"] is True
    assert report["generic_lifecycle_completion_audit_execution_allowed"] is False
    assert report["paper_lifecycle_completion_ready"] is False
    assert report["would_run_lifecycle_completion_audit"] is False
    reasons = report["generic_supervised_paper_lifecycle_completion_audit_execution_map"]["lifecycle_completion_audit_execution_gate_model"]["lifecycle_completion_audit_execution_blocked_reasons"]
    assert "postmortem_runtime_execution_absent" in reasons
    assert "final_audit_runtime_execution_absent" in reasons
    assert "broker_close_receipt_absent" in reasons
