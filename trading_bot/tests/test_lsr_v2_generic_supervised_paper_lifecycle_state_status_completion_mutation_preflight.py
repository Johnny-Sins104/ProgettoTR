from __future__ import annotations

import json
import os
from pathlib import Path

from trading_bot.core.lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight import (
    READY_DECISION,
    REQUIRED_ORDER_INTENT_FIELDS,
    Settings,
    _write_json,
    run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight,
)

REQUIRED = list(REQUIRED_ORDER_INTENT_FIELDS)


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
        "trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution.py": (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION\n"
            "generic_lifecycle_completion_audit_execution_ready\n"
        ),
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "import argparse\n",
    }
    for rel, text in paths.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _u43_report() -> dict:
    completion_map = {
        "dry_run_order_intent_payload": _dry_run_payload(),
        "lifecycle_completion_audit_execution_patch": True,
        "lifecycle_completion_audit_execution_gate_model": {
            "lifecycle_completion_audit_execution_model_ready": True,
            "lifecycle_completion_audit_execution_gate_model_ready": True,
            "lifecycle_completion_audit_execution_conditions_satisfied": False,
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
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_READY",
        "generic_supervised_paper_lifecycle_completion_audit_execution_ready": True,
        "generic_lifecycle_completion_audit_execution_ready": True,
        "generic_lifecycle_completion_audit_execution_model_ready": True,
        "generic_lifecycle_completion_audit_execution_patch_ready": True,
        "paper_lifecycle_completion_audit_execution_ready": True,
        "lifecycle_completion_audit_execution_diagnostic_available": True,
        "lifecycle_completion_audit_execution_diagnostic_count": 401,
        "lifecycle_completion_audit_execution_contract_present_fields": REQUIRED,
        "lifecycle_completion_audit_execution_contract_required_fields": REQUIRED,
        "lifecycle_completion_audit_execution_contract_missing_fields": [],
        "generic_supervised_paper_lifecycle_completion_audit_execution_map": completion_map,
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
        "generic_final_audit_execution_allowed",
        "generic_postmortem_execution_allowed",
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


def test_state_status_completion_mutation_preflight_ready_but_mutation_blocked(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_report.json", _u43_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_preflight_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_preflight_model_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_preflight_patch_ready"] is True
    assert report["paper_lifecycle_state_status_completion_mutation_preflight_ready"] is True
    assert report["lifecycle_state_status_completion_mutation_preflight_diagnostic_available"] is True
    assert report["lifecycle_state_status_completion_mutation_preflight_diagnostic_count"] == 401
    assert report["lifecycle_state_status_completion_mutation_preflight_contract_shape_modelable"] is True
    assert report["lifecycle_state_status_completion_mutation_preflight_contract_missing_fields"] == []
    assert report["generic_lifecycle_state_status_completion_mutation_allowed"] is False
    assert report["generic_paper_state_mutation_allowed"] is False
    assert report["generic_paper_status_mutation_allowed"] is False
    assert report["paper_lifecycle_state_status_completion_mutation_ready"] is False
    assert report["would_mutate_paper_state"] is False
    assert report["would_mutate_paper_status"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False
    assert report["orders_submitted_by_generic_lifecycle_state_status_completion_mutation_preflight"] == 0
    assert report["paper_state_modified_by_generic_lifecycle_state_status_completion_mutation_preflight"] is False
    assert report["paper_status_modified_by_generic_lifecycle_state_status_completion_mutation_preflight"] is False
    state_status_map = report["generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_map"]
    assert state_status_map["lifecycle_state_status_completion_mutation_preflight_patch"] is True
    assert state_status_map["mode"] == "generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_only"
    gate = state_status_map["lifecycle_state_status_completion_mutation_preflight_gate_model"]
    assert gate["lifecycle_state_status_completion_mutation_preflight_model_ready"] is True
    assert gate["lifecycle_state_status_completion_mutation_allowed"] is False
    assert "explicit_lifecycle_state_status_completion_mutation_execution_patch_required" in gate[
        "lifecycle_state_status_completion_mutation_blocked_reasons"
    ]


def test_state_status_completion_mutation_preflight_writes_report_and_jsonl(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_report.json", _u43_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["decision"] == READY_DECISION
    assert persisted["would_mutate_paper_state"] is False
    assert persisted["would_mutate_paper_status"] is False
    assert json.loads(jsonl_path.read_text(encoding="utf-8").strip().splitlines()[-1])["decision"] == READY_DECISION
    assert report["read_only_verified"] is True


def test_state_status_completion_mutation_preflight_operator_gate_remains_fail_closed(tmp_path, monkeypatch):
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_report.json", _u43_report())
    monkeypatch.setenv("LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ENABLE", "1")
    monkeypatch.setenv(
        "LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_CONFIRMATION",
        "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ONLY",
    )

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight(_settings(tmp_path))

    gate = report["generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_map"][
        "lifecycle_state_status_completion_mutation_preflight_gate_model"
    ]
    assert gate["operator_lifecycle_state_status_completion_mutation_gate_satisfied"] is True
    assert gate["lifecycle_state_status_completion_mutation_allowed"] is False
    assert report["generic_paper_state_mutation_allowed"] is False
    assert report["generic_paper_status_mutation_allowed"] is False
    assert report["active_lsr_v2_operator_env_count"] == 2


def test_state_status_completion_mutation_preflight_missing_source_marker_keeps_diagnostic(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_report.json", _u43_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"].startswith("KEEP_DIAGNOSTIC_LSR_V2")
    assert "source_markers_missing" in report["blockers"]
    assert report["would_mutate_paper_state"] is False
    assert report["would_mutate_paper_status"] is False


def test_state_status_completion_mutation_preflight_fail_closed_flags(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_report.json", _u43_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight(_settings(tmp_path))

    assert report["all_execution_flags_fail_closed"] is True
    false_keys = [
        "generic_submit_execution_allowed",
        "generic_close_execution_allowed",
        "generic_lifecycle_completion_audit_execution_allowed",
        "generic_lifecycle_state_status_completion_mutation_allowed",
        "generic_paper_state_completion_mutation_allowed",
        "generic_paper_status_completion_mutation_allowed",
        "generic_paper_state_mutation_allowed",
        "generic_paper_status_mutation_allowed",
        "paper_engine_mutation_allowed",
        "runner_mutation_allowed",
        "launcher_mutation_allowed",
        "paper_only_execution_allowed",
    ]
    assert all(report[key] is False for key in false_keys)
    stages = report["generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight_map"]["stages"]
    assert stages
    assert all(stage["execution_allowed"] is False for stage in stages)
    assert all(stage["state_mutation_allowed"] is False for stage in stages)
