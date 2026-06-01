from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_order_intent_activation import (
    FALSE_EXECUTION_KEYS,
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_order_intent_activation,
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
    (core / "lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py").write_text(
        "GENERIC_LSR_V2_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT\n"
        "generic_supervised_paper_order_intent_activation_preflight_ready\n",
        encoding="utf-8",
    )
    (core / "paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _dry_run_payload() -> dict:
    return {
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


def _u27_report() -> dict:
    activation_preflight_map = {
        "mode": "generic_supervised_paper_order_intent_activation_preflight_only",
        "paper_only": True,
        "preflight_only": True,
        "read_only": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "dry_run_order_intent_payload": _dry_run_payload(),
        "required_contract_fields": REQUIRED,
        "present_contract_fields": REQUIRED,
        "missing_contract_fields": [],
        "activation_preflight_contract": {
            "activation_preflight_model_ready": True,
            "submit_execution_scaffold_contract_shape_modelable": True,
            "contract_runtime_value_validation_deferred": True,
            "runtime_values_present": False,
            "runtime_values_required_before_real_activation": True,
            "max_open_positions": 1,
            "max_open_positions_valid": True,
            "paper_only": True,
            "paper_only_valid": True,
            "operator_rearm_gate_required": True,
            "operator_rearm_gate_satisfied": False,
            "real_order_intent_activation_allowed": False,
            "order_intent_persistence_allowed": False,
            "submit_candidate_creation_allowed": False,
            "submit_execution_allowed": False,
            "broker_submit_allowed": False,
            "missing_model_fields": [],
            "present_model_fields": REQUIRED,
            "required_model_fields": REQUIRED,
        },
    }
    report = {
        "prompt": "29.4.4u-27",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT_READY",
        "generic_supervised_paper_order_intent_activation_preflight_ready": True,
        "generic_order_intent_activation_preflight_ready": True,
        "paper_order_intent_activation_preflight_ready": True,
        "generic_order_intent_activation_preflight_map": activation_preflight_map,
        "order_intent_activation_preflight_diagnostic_available": True,
        "order_intent_activation_preflight_diagnostic_count": 401,
        "order_intent_activation_contract_shape_modelable": True,
        "order_intent_activation_contract_required_fields": REQUIRED,
        "order_intent_activation_contract_present_fields": REQUIRED,
        "order_intent_activation_contract_missing_fields": [],
        "generic_supervised_paper_submit_execution_scaffold_ready": True,
        "generic_submit_execution_scaffold_ready": True,
        "paper_submit_execution_scaffold_ready": True,
        "submit_execution_scaffold_diagnostic_available": True,
        "submit_execution_scaffold_diagnostic_count": 401,
        "submit_execution_scaffold_contract_shape_modelable": True,
        "submit_candidate_audit_diagnostic_available": True,
        "submit_candidate_audit_diagnostic_count": 401,
        "submit_candidate_contract_shape_modelable": True,
        "generic_submit_candidate_audit_ready": True,
        "paper_submit_candidate_audit_ready": True,
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
            {"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY"}
        ],
        "paper_order_intent_dry_run_ready": True,
        "paper_order_intent_materialization_dry_run_ready": True,
        "paper_order_intent_materialization_simulated": True,
        "would_materialize_order_intent_dry_run": True,
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_values_required_before_real_activation": True,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_activation_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "generic_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_ready": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "paper_broker_submit_allowed": False,
        "generic_order_intent_activation_allowed": False,
        "would_validate_order_intent": False,
        "would_activate_order_intent": False,
        "would_create_order_intent": False,
        "would_materialize_order_intent_real": False,
        "would_persist_order_intent": False,
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
        "paper_state_modified_by_generic_order_intent_activation_preflight": False,
        "paper_status_modified_by_generic_order_intent_activation_preflight": False,
        "orders_submitted_by_generic_order_intent_activation_preflight": 0,
        "positions_opened_by_generic_order_intent_activation_preflight": 0,
        "positions_closed_by_generic_order_intent_activation_preflight": 0,
        "broker_submit_called_by_generic_order_intent_activation_preflight": False,
        "broker_close_called_by_generic_order_intent_activation_preflight": False,
    }
    for key in FALSE_EXECUTION_KEYS:
        report[key] = False
    report.update(
        {
            "generic_order_intent_activation_allowed": False,
            "generic_order_intent_persistence_allowed": False,
        }
    )
    return report


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir="data")


def test_order_intent_activation_ready_but_no_real_activation_without_gate_or_runtime_values(tmp_path, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json",
        _u27_report(),
    )

    report = run_generic_supervised_paper_order_intent_activation(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_order_intent_activation_ready"] is True
    assert report["generic_order_intent_activation_model_ready"] is True
    assert report["generic_rearm_operator_gate_required"] is True
    assert report["generic_rearm_operator_gate_satisfied"] is False
    assert report["paper_order_intent_runtime_values_present"] is False
    assert report["generic_order_intent_activation_allowed"] is False
    assert report["paper_order_intent_activation_ready"] is False
    assert report["paper_order_intent_materialized"] is False
    assert report["paper_order_intent_persisted"] is False
    assert report["would_activate_order_intent"] is False
    assert report["would_create_order_intent"] is False
    assert report["would_materialize_order_intent_real"] is False
    assert report["would_persist_order_intent"] is False
    assert report["would_submit"] is False
    assert report["orders_submitted_by_generic_order_intent_activation"] == 0
    assert report["positions_opened_by_generic_order_intent_activation"] == 0
    assert report["paper_state_modified_by_generic_order_intent_activation"] is False
    assert report["paper_status_modified_by_generic_order_intent_activation"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_order_intent_activation_requires_upstream_preflight_report(tmp_path):
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_order_intent_activation(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "missing_upstream_reports" in report["blockers"]
    assert report["generic_supervised_paper_order_intent_activation_ready"] is False


def test_order_intent_activation_requires_source_markers(tmp_path):
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json",
        _u27_report(),
    )

    report = run_generic_supervised_paper_order_intent_activation(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "source_markers_present" in report["blockers"]
    assert report["generic_order_intent_activation_source_files_present"] is False


def test_order_intent_activation_fails_closed_if_operator_env_is_set_during_validation(tmp_path, monkeypatch):
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json",
        _u27_report(),
    )
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_CONFIRMATION", "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_MAX_POSITIONS", "1")

    report = run_generic_supervised_paper_order_intent_activation(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["generic_rearm_operator_gate_satisfied"] is True
    assert report["paper_order_intent_runtime_values_present"] is False
    assert report["generic_order_intent_activation_allowed"] is False
    assert report["would_activate_order_intent"] is False
    assert "operator_env_absent" in report["blockers"]
    assert "operator_rearm_gate_not_satisfied" in report["blockers"]


def test_order_intent_activation_writes_report_and_jsonl(tmp_path, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json",
        _u27_report(),
    )

    report = run_generic_supervised_paper_order_intent_activation(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_order_intent_activation.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    stored = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored["decision"] == READY_DECISION
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[-1])["event_type"] == report["event_type"]
