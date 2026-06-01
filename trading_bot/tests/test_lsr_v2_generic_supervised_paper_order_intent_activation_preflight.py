from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_order_intent_activation_preflight import (
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_order_intent_activation_preflight,
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

DEFERRED = "deferred_until_explicit_order_intent_patch"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markers(root: Path) -> None:
    core = root / "trading_bot/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "lsr_v2_generic_supervised_paper_submit_execution_scaffold.py").write_text(
        "GENERIC_LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION_SCAFFOLD\n"
        "generic_supervised_paper_submit_execution_scaffold_ready\n",
        encoding="utf-8",
    )
    (core / "paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _dry_run_payload(**overrides) -> dict:
    payload = {
        "symbol": DEFERRED,
        "side": DEFERRED,
        "entry_price": DEFERRED,
        "stop_loss": DEFERRED,
        "take_profit": DEFERRED,
        "risk_amount": DEFERRED,
        "position_size": DEFERRED,
        "max_open_positions": 1,
        "paper_only": True,
        "dry_run_only": True,
        "materialized": False,
        "persisted": False,
        "runtime_values_present": False,
    }
    payload.update(overrides)
    return payload


def _u26_report(**overrides) -> dict:
    payload = overrides.pop("dry_run_payload", _dry_run_payload())
    scaffold_map = {
        "mode": "generic_supervised_paper_submit_execution_scaffold_only",
        "paper_only": True,
        "scaffold_only": True,
        "read_only": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": REQUIRED,
        "present_contract_fields": REQUIRED,
        "missing_contract_fields": [],
        "submit_execution_scaffold_contract": {
            "scaffold_model_ready": True,
            "submit_candidate_contract_shape_modelable": True,
            "contract_runtime_value_validation_deferred": True,
            "runtime_values_present": False,
            "runtime_values_required_before_submit_execution": True,
            "real_order_intent_required_before_execution": True,
            "paper_order_intent_persistence_required_before_execution": True,
            "submit_candidate_creation_required_before_execution": True,
            "max_open_positions": 1,
            "max_open_positions_valid": payload.get("max_open_positions") == 1,
            "paper_only": True,
            "paper_only_valid": payload.get("paper_only") is True,
            "operator_submit_gate_required": True,
            "operator_submit_gate_satisfied": False,
            "broker_submit_allowed": False,
            "submit_execution_allowed": False,
            "missing_model_fields": [],
            "present_model_fields": REQUIRED,
            "required_model_fields": REQUIRED,
        },
        "supervised_submit_execution_scaffold_context": {
            "submit_execution_scaffold_ready": True,
            "paper_submit_execution_scaffold_ready": True,
            "generic_submit_execution_scaffold_ready": True,
            "paper_submit_candidate_ready": False,
            "generic_submit_candidate_ready": False,
            "paper_order_intent_ready": False,
            "paper_order_intent_validated": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_runtime_values_present": False,
            "paper_submit_execution_ready": False,
            "generic_submit_execution_allowed": False,
            "paper_broker_submit_allowed": False,
            "would_call_paper_broker_submit": False,
            "would_submit": False,
        },
    }
    report = {
        "prompt": "29.4.4u-26",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_SUBMIT_EXECUTION_SCAFFOLD_READY",
        "generic_supervised_paper_submit_execution_scaffold_ready": True,
        "generic_submit_execution_scaffold_ready": True,
        "paper_submit_execution_scaffold_ready": True,
        "generic_submit_execution_scaffold_contract_ready": True,
        "generic_submit_execution_scaffold_gate_model_ready": True,
        "generic_submit_execution_scaffold_map_ready": True,
        "generic_submit_execution_scaffold_map": scaffold_map,
        "submit_execution_scaffold_diagnostic_available": True,
        "submit_execution_scaffold_diagnostic_count": 401,
        "submit_execution_scaffold_contract_shape_modelable": True,
        "submit_execution_scaffold_contract_required_fields": REQUIRED,
        "submit_execution_scaffold_contract_present_fields": REQUIRED,
        "submit_execution_scaffold_contract_missing_fields": [],
        "generic_submit_candidate_audit_ready": True,
        "paper_submit_candidate_audit_ready": True,
        "submit_candidate_audit_diagnostic_available": True,
        "submit_candidate_audit_diagnostic_count": 401,
        "submit_candidate_contract_shape_modelable": True,
        "generic_submit_readiness_preflight_ready": True,
        "paper_submit_readiness_preflight_ready": True,
        "generic_order_intent_materialization_dry_run_ready": True,
        "order_intent_materialization_dry_run_ready": True,
        "order_intent_validation_preflight_ready": True,
        "paper_order_intent_contract_ready": True,
        "paper_order_intent_contract_validatable": True,
        "paper_order_intent_contract_validation_preflight_ready": True,
        "order_intent_candidate_audit_diagnostic_available": True,
        "order_intent_candidate_audit_diagnostic_count": 401,
        "candidate_detection_source_counts": {
            "paper_events_jsonl_diagnostic_read": 400,
            "strategy_signal_diagnostic_read": 1,
        },
        "candidate_diagnostic_examples": [
            {"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY", "route_candidate_available": False}
        ],
        "paper_order_intent_dry_run_ready": True,
        "paper_order_intent_materialization_dry_run_ready": True,
        "paper_order_intent_materialization_simulated": True,
        "would_materialize_order_intent_dry_run": True,
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_values_required_before_submit_execution": True,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "generic_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_ready": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "paper_broker_submit_allowed": False,
        "would_validate_order_intent": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_prepare_submit_candidate": False,
        "would_call_paper_broker_submit": False,
        "would_submit": False,
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "paper_state_status_consistency": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "paper_state_modified_by_generic_submit_execution_scaffold": False,
        "paper_status_modified_by_generic_submit_execution_scaffold": False,
        "orders_submitted_by_generic_submit_execution_scaffold": 0,
        "positions_opened_by_generic_submit_execution_scaffold": 0,
        "positions_closed_by_generic_submit_execution_scaffold": 0,
        "broker_submit_called_by_generic_submit_execution_scaffold": False,
        "broker_close_called_by_generic_submit_execution_scaffold": False,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_candidate_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_order_intent_candidate_materialization_allowed": False,
        "generic_order_intent_validation_allowed": False,
        "generic_order_intent_validation_execution_allowed": False,
        "generic_order_intent_materialization_allowed": False,
        "generic_order_intent_creation_allowed": False,
        "generic_order_intent_dry_run_execution_allowed": False,
        "generic_order_intent_persistence_allowed": False,
        "generic_submit_readiness_preflight_allowed": False,
        "generic_submit_candidate_audit_allowed": False,
        "generic_submit_candidate_creation_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
    }
    report.update(overrides)
    return report


def test_activation_preflight_passes_with_u26_scaffold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_CONFIRMATION", raising=False)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_MAX_POSITIONS", raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json", _u26_report())

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_order_intent_activation_preflight_ready"] is True
    assert report["generic_order_intent_activation_preflight_ready"] is True
    assert report["paper_order_intent_activation_preflight_ready"] is True
    assert report["order_intent_activation_preflight_diagnostic_available"] is True
    assert report["order_intent_activation_contract_shape_modelable"] is True
    assert report["generic_rearm_operator_gate_required"] is True
    assert report["generic_rearm_operator_gate_satisfied"] is False
    assert report["generic_order_intent_activation_allowed"] is False
    assert report["paper_order_intent_activation_ready"] is False
    assert report["paper_order_intent_ready"] is False
    assert report["paper_order_intent_materialized"] is False
    assert report["paper_order_intent_persisted"] is False
    assert report["would_activate_order_intent"] is False
    assert report["would_create_order_intent"] is False
    assert report["would_submit"] is False
    assert report["orders_submitted_by_generic_order_intent_activation_preflight"] == 0
    assert report["positions_opened_by_generic_order_intent_activation_preflight"] == 0
    assert report["paper_state_modified_by_generic_order_intent_activation_preflight"] is False
    assert report["paper_status_modified_by_generic_order_intent_activation_preflight"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_activation_preflight_warns_when_upstream_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert any(item.startswith("missing_upstream:") for item in report["blockers"])
    assert report["generic_order_intent_activation_preflight_ready"] is False
    assert report["would_create_order_intent"] is False
    assert report["would_submit"] is False


def test_activation_preflight_warns_when_scaffold_not_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json",
        _u26_report(generic_supervised_paper_submit_execution_scaffold_ready=False),
    )

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "submit_execution_scaffold_report_ready" in report["blockers"]
    assert report["paper_order_intent_activation_preflight_ready"] is False


def test_activation_preflight_warns_when_contract_policy_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json",
        _u26_report(dry_run_payload=_dry_run_payload(max_open_positions=2, paper_only=False)),
    )

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "paper_only_policy_ready" in report["blockers"]
    assert "single_position_policy_ready" in report["blockers"]
    assert report["generic_order_intent_activation_allowed"] is False


def test_activation_preflight_warns_when_runtime_values_already_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    payload = _dry_run_payload(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        risk_amount=10.0,
        position_size=0.1,
        runtime_values_present=True,
    )
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json",
        _u26_report(dry_run_payload=payload, paper_order_intent_runtime_values_present=True),
    )

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "runtime_values_not_present" in report["blockers"]
    assert report["paper_order_intent_ready"] is False
    assert report["would_activate_order_intent"] is False


def test_activation_preflight_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_CONFIRMATION", "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_MAX_POSITIONS", "1")
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json", _u26_report())

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "operator_rearm_gate_not_satisfied" in report["blockers"]
    assert "operator_env_absent" in report["blockers"]
    assert report["generic_rearm_operator_gate_satisfied"] is True
    assert report["would_create_order_intent"] is False


def test_activation_preflight_writes_report_and_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_submit_execution_scaffold_report.json", _u26_report())

    report = run_generic_supervised_paper_order_intent_activation_preflight(Settings(project_root=tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == report["decision"]
    assert "GENERIC_ORDER_INTENT_ACTIVATION_PREFLIGHT_READY" in saved["classification_labels"]
