from __future__ import annotations

import json
import os
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_close_execution_scaffold import (
    FALSE_EXECUTION_KEYS,
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_close_execution_scaffold,
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
    (core / "lsr_v2_generic_supervised_paper_close_preflight.py").write_text(
        "GENERIC_LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT\n"
        "generic_supervised_paper_close_preflight_ready\n",
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


def _u31_report() -> dict:
    close_map = {
        "mode": "generic_supervised_paper_close_preflight_only",
        "paper_only": True,
        "preflight_source": "29.4.4u-30",
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
        "close_preflight_context": {
            "blocked_reason": "close_preflight_blocked_until_real_open_position_monitor_and_close_trigger",
            "generic_close_preflight_ready": True,
            "paper_close_preflight_ready": True,
            "broker_submit_receipt_available": False,
            "open_position_available": False,
            "paper_position_open": False,
            "paper_open_position_monitor_ready": False,
            "close_trigger_available": False,
            "generic_close_execution_allowed": False,
            "paper_close_execution_ready": False,
            "broker_close_allowed": False,
            "would_prepare_close": False,
            "would_call_paper_broker_close": False,
            "would_close": False,
            "would_submit": False,
        },
        "close_preflight_gate_model": {
            "close_preflight_model_ready": True,
            "close_preflight_allowed": False,
            "broker_submit_receipt_required": True,
            "broker_submit_receipt_available": False,
            "paper_open_position_required": True,
            "paper_open_position_available": False,
            "open_position_monitor_ready_required": True,
            "paper_open_position_monitor_ready": False,
            "close_trigger_required": True,
            "close_trigger_available": False,
            "operator_rearm_gate_required": True,
            "operator_rearm_gate_satisfied": False,
            "operator_submit_gate_required": True,
            "operator_submit_gate_satisfied": False,
            "operator_close_gate_required": True,
            "operator_close_gate_satisfied": False,
            "runtime_values_required_before_close_preflight": True,
            "runtime_values_present": False,
            "max_open_positions": 1,
            "max_open_positions_valid": True,
            "paper_only": True,
            "paper_only_valid": True,
            "close_execution_allowed": False,
            "broker_close_allowed": False,
            "missing_model_fields": [],
            "present_model_fields": REQUIRED,
            "required_model_fields": REQUIRED,
        },
    }
    report = {
        "prompt": "29.4.4u-31",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_CLOSE_PREFLIGHT_READY",
        "generic_supervised_paper_close_preflight_ready": True,
        "generic_close_preflight_ready": True,
        "paper_close_preflight_ready": True,
        "generic_close_preflight_model_ready": True,
        "close_preflight_diagnostic_available": True,
        "close_preflight_diagnostic_count": 401,
        "close_preflight_contract_shape_modelable": True,
        "close_preflight_contract_required_fields": REQUIRED,
        "close_preflight_contract_present_fields": REQUIRED,
        "close_preflight_contract_missing_fields": [],
        "generic_supervised_paper_close_preflight_map": close_map,
        "generic_supervised_paper_open_position_monitor_preflight_map": {"dry_run_order_intent_payload": _dry_run_payload()},
        "generic_supervised_paper_submit_execution_map": {"dry_run_order_intent_payload": _dry_run_payload()},
        "open_position_monitor_preflight_diagnostic_available": True,
        "open_position_monitor_preflight_diagnostic_count": 401,
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400, "strategy_signal_diagnostic_read": 1},
        "candidate_diagnostic_examples": [{"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY"}],
        "broker_submit_receipt_available": False,
        "paper_open_position_available": False,
        "paper_position_open": False,
        "paper_open_position_monitor_ready": False,
        "close_trigger_available": False,
        "paper_close_execution_ready": False,
        "generic_close_execution_allowed": False,
        "broker_close_allowed": False,
        "would_prepare_close": False,
        "would_call_paper_broker_close": False,
        "would_close": False,
        "would_submit": False,
        "would_materialize_order_intent_dry_run": True,
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_values_required_before_close_preflight": True,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_validated": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "generic_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_ready": False,
        "generic_submit_execution_allowed": False,
        "paper_broker_submit_allowed": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": False,
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
        "paper_state_modified_by_generic_close_preflight": False,
        "paper_status_modified_by_generic_close_preflight": False,
        "orders_submitted_by_generic_close_preflight": 0,
        "positions_opened_by_generic_close_preflight": 0,
        "positions_closed_by_generic_close_preflight": 0,
        "broker_submit_called_by_generic_close_preflight": False,
        "broker_close_called_by_generic_close_preflight": False,
    }
    for key in FALSE_EXECUTION_KEYS:
        report[key] = False
    return report


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir="data")


def test_close_execution_scaffold_ready_but_no_close_without_position_trigger_or_gates(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_close_preflight_report.json", _u31_report())

    report = run_generic_supervised_paper_close_execution_scaffold(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_close_execution_scaffold_ready"] is True
    assert report["generic_close_execution_scaffold_ready"] is True
    assert report["paper_close_execution_scaffold_ready"] is True
    assert report["close_execution_scaffold_diagnostic_available"] is True
    assert report["close_execution_scaffold_diagnostic_count"] == 401
    assert report["close_execution_scaffold_contract_shape_modelable"] is True
    assert report["close_execution_scaffold_contract_missing_fields"] == []
    assert report["generic_supervised_paper_close_preflight_ready"] is True
    assert report["broker_submit_receipt_available"] is False
    assert report["paper_open_position_available"] is False
    assert report["paper_position_open"] is False
    assert report["paper_open_position_monitor_ready"] is False
    assert report["close_trigger_available"] is False
    assert report["generic_close_execution_allowed"] is False
    assert report["paper_close_execution_ready"] is False
    assert report["broker_close_allowed"] is False
    assert report["would_prepare_close"] is False
    assert report["would_call_paper_broker_close"] is False
    assert report["would_close"] is False
    assert report["would_submit"] is False
    assert report["would_reconcile_realized_pnl"] is False
    assert report["orders_submitted_by_generic_close_execution_scaffold"] == 0
    assert report["positions_opened_by_generic_close_execution_scaffold"] == 0
    assert report["positions_closed_by_generic_close_execution_scaffold"] == 0
    assert report["paper_state_modified_by_generic_close_execution_scaffold"] is False
    assert report["paper_status_modified_by_generic_close_execution_scaffold"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_close_execution_scaffold_requires_upstream_close_preflight_report(tmp_path):
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_close_execution_scaffold(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "missing_upstream_reports" in report["blockers"]
    assert report["generic_supervised_paper_close_execution_scaffold_ready"] is False


def test_close_execution_scaffold_requires_source_markers(tmp_path):
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_close_preflight_report.json", _u31_report())

    report = run_generic_supervised_paper_close_execution_scaffold(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert "source_markers_present" in report["blockers"]
    assert report["source_markers_present"] is False


def test_close_execution_scaffold_blocks_when_operator_env_is_present(tmp_path, monkeypatch):
    monkeypatch.setenv("LSR_V2_GENERIC_CLOSE_ENABLE", "1")
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_close_preflight_report.json", _u31_report())

    report = run_generic_supervised_paper_close_execution_scaffold(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1


def test_close_execution_scaffold_writes_report_and_jsonl(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_close_preflight_report.json", _u31_report())

    report = run_generic_supervised_paper_close_execution_scaffold(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_close_execution_scaffold_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_close_execution_scaffold.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["decision"] == READY_DECISION
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[-1])["event_type"] == report["event_type"]
