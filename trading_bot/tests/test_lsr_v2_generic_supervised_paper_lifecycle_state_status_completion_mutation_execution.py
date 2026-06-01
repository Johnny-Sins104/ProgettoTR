from __future__ import annotations

import os
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution import (
    READY_DECISION,
    REQUIRED_ORDER_INTENT_FIELDS,
    Settings,
    run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution,
)


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
        "trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold.py": (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_EXECUTION_SCAFFOLD\n"
            "generic_lifecycle_state_status_completion_mutation_execution_scaffold_ready\n"
        ),
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "import argparse\n",
    }
    for rel, text in paths.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _u45_report() -> dict:
    source_gate = {
        "lifecycle_state_status_completion_mutation_execution_scaffold_model_ready": True,
        "lifecycle_state_status_completion_mutation_execution_scaffold_gate_model_ready": True,
        "lifecycle_state_status_completion_mutation_execution_scaffold_conditions_satisfied": False,
        "lifecycle_state_status_completion_mutation_execution_scaffold_allowed": False,
        "runtime_values_present": False,
    }
    source_map = {
        "dry_run_order_intent_payload": _dry_run_payload(),
        "lifecycle_state_status_completion_mutation_execution_scaffold_patch": True,
        "lifecycle_state_status_completion_mutation_execution_scaffold_gate_model": source_gate,
    }
    false_values = {
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
        "lifecycle_completion_audit_runtime_executed": False,
        "generic_lifecycle_state_status_completion_mutation_allowed": False,
        "generic_lifecycle_state_status_completion_mutation_execution_allowed": False,
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
        "lifecycle_state_complete": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    }
    return {
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_EXECUTION_SCAFFOLD_READY",
        "generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_ready": True,
        "generic_lifecycle_state_status_completion_mutation_execution_scaffold_ready": True,
        "generic_lifecycle_state_status_completion_mutation_execution_scaffold_model_ready": True,
        "generic_lifecycle_state_status_completion_mutation_execution_scaffold_patch_ready": True,
        "paper_lifecycle_state_status_completion_mutation_execution_scaffold_ready": True,
        "lifecycle_state_status_completion_mutation_execution_scaffold_diagnostic_available": True,
        "lifecycle_state_status_completion_mutation_execution_scaffold_diagnostic_count": 401,
        "generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_map": source_map,
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400, "strategy_signal_diagnostic_read": 1},
        "candidate_diagnostic_examples": [{"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY"}],
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        **false_values,
    }


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir="data")


def test_execution_ready_but_mutation_blocked(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_report.json", _u45_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_execution_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_execution_model_ready"] is True
    assert report["generic_lifecycle_state_status_completion_mutation_execution_patch_ready"] is True
    assert report["paper_lifecycle_state_status_completion_mutation_execution_ready"] is True
    assert report["lifecycle_state_status_completion_mutation_execution_diagnostic_available"] is True
    assert report["lifecycle_state_status_completion_mutation_execution_diagnostic_count"] == 401
    assert report["lifecycle_state_status_completion_mutation_execution_contract_shape_modelable"] is True
    assert report["lifecycle_state_status_completion_mutation_execution_contract_missing_fields"] == []
    assert report["generic_lifecycle_state_status_completion_mutation_allowed"] is False
    assert report["generic_lifecycle_state_status_completion_mutation_execution_allowed"] is False
    assert report["generic_paper_state_mutation_allowed"] is False
    assert report["generic_paper_status_mutation_allowed"] is False
    assert report["paper_lifecycle_state_status_completion_mutation_ready"] is False
    assert report["would_mutate_paper_state"] is False
    assert report["would_mutate_paper_status"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False
    assert report["orders_submitted_by_generic_lifecycle_state_status_completion_mutation_execution"] == 0
    assert report["paper_state_modified_by_generic_lifecycle_state_status_completion_mutation_execution"] is False
    assert report["paper_status_modified_by_generic_lifecycle_state_status_completion_mutation_execution"] is False
    state_status_map = report["generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_map"]
    assert state_status_map["lifecycle_state_status_completion_mutation_execution_patch"] is True
    assert state_status_map["mode"] == "generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_controlled"
    gate = state_status_map["lifecycle_state_status_completion_mutation_execution_gate_model"]
    assert gate["lifecycle_state_status_completion_mutation_execution_model_ready"] is True
    assert gate["lifecycle_state_status_completion_mutation_execution_allowed"] is False
    assert "runtime_values_absent_or_deferred" in gate["lifecycle_state_status_completion_mutation_execution_blocked_reasons"]
    assert "explicit_lifecycle_state_status_completion_mutation_execution_patch_required" not in gate["lifecycle_state_status_completion_mutation_execution_blocked_reasons"]


def test_execution_writes_report_and_jsonl(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_report.json", _u45_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    assert "NO_STATE_MUTATION" in report["classification_labels"]
    assert "NO_STATUS_MUTATION" in report["classification_labels"]
    assert report["read_only_verified"] is True
    assert report["all_execution_flags_fail_closed"] is True


def test_execution_fails_closed_when_source_markers_missing(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_report.json", _u45_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert report["generic_lifecycle_state_status_completion_mutation_execution_allowed"] is False
    assert report["would_mutate_paper_state"] is False
    assert report["would_mutate_paper_status"] is False
    assert report["source_markers_present"] is False


def test_execution_operator_env_does_not_enable_mutation(tmp_path, monkeypatch):
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_report.json", _u45_report())
    monkeypatch.setenv("LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ENABLE", "1")
    monkeypatch.setenv(
        "LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_CONFIRMATION",
        "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ONLY",
    )

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["active_lsr_v2_operator_env_count"] == 2
    assert report["operator_env_absent"] is False
    assert report["generic_lifecycle_state_status_completion_mutation_execution_allowed"] is False
    assert report["generic_paper_state_mutation_allowed"] is False
    assert report["generic_paper_status_mutation_allowed"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False


def test_execution_contract_fields_are_stable(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_scaffold_report.json", _u45_report())

    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(_settings(tmp_path))

    required = list(REQUIRED_ORDER_INTENT_FIELDS)
    assert report["lifecycle_state_status_completion_mutation_execution_contract_required_fields"] == required
    assert report["lifecycle_state_status_completion_mutation_execution_contract_present_fields"] == required
    gate = report["generic_supervised_paper_lifecycle_state_status_completion_mutation_execution_map"]["lifecycle_state_status_completion_mutation_execution_gate_model"]
    assert gate["max_open_positions"] == 1
    assert gate["paper_only"] is True
    assert gate["runtime_values_present"] is False
