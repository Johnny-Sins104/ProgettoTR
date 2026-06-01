from __future__ import annotations

import json
import os
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_final_audit_preflight import (
    FALSE_EXECUTION_KEYS,
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_final_audit_preflight,
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
    (core / "lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight.py").write_text(
        "GENERIC_LSR_V2_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT\n"
        "generic_realized_pnl_reconciliation_preflight_ready\n",
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


def _u34_report() -> dict:
    pnl_map = {
        "mode": "generic_supervised_paper_realized_pnl_reconciliation_preflight_only",
        "paper_only": True,
        "preflight_source": "29.4.4u-33",
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
        "realized_pnl_reconciliation_preflight_context": {
            "blocked_reason": "realized_pnl_reconciliation_blocked_until_real_close_receipt_and_closed_position",
            "generic_supervised_paper_realized_pnl_reconciliation_preflight_ready": True,
            "generic_realized_pnl_reconciliation_preflight_ready": True,
            "paper_realized_pnl_reconciliation_preflight_ready": True,
            "broker_submit_receipt_available": False,
            "broker_close_receipt_available": False,
            "real_close_execution_available": False,
            "paper_position_closed": False,
            "paper_realized_pnl_reconciliation_ready": False,
            "would_reconcile_realized_pnl": False,
            "would_write_realized_pnl": False,
            "would_run_final_audit": False,
            "would_run_postmortem": False,
            "would_submit": False,
            "would_close": False,
        },
        "realized_pnl_reconciliation_gate_model": {
            "realized_pnl_reconciliation_preflight_model_ready": True,
            "realized_pnl_reconciliation_allowed": False,
            "broker_submit_receipt_available": False,
            "broker_close_receipt_available": False,
            "real_close_execution_available": False,
            "paper_position_closed": False,
            "operator_rearm_gate_satisfied": False,
            "operator_submit_gate_satisfied": False,
            "operator_close_gate_satisfied": False,
            "operator_realized_pnl_gate_satisfied": False,
            "runtime_values_present": False,
            "final_audit_execution_allowed": False,
            "postmortem_execution_allowed": False,
            "state_mutation_allowed_during_preflight": False,
            "missing_model_fields": [],
            "present_model_fields": REQUIRED,
            "required_model_fields": REQUIRED,
        },
    }
    report = {
        "prompt": "29.4.4u-34",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_READY",
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_ready": True,
        "generic_realized_pnl_reconciliation_preflight_ready": True,
        "generic_realized_pnl_reconciliation_preflight_model_ready": True,
        "generic_realized_pnl_reconciliation_preflight_patch_ready": True,
        "paper_realized_pnl_reconciliation_preflight_ready": True,
        "realized_pnl_reconciliation_preflight_diagnostic_available": True,
        "realized_pnl_reconciliation_preflight_diagnostic_count": 401,
        "realized_pnl_reconciliation_contract_shape_modelable": True,
        "realized_pnl_reconciliation_contract_required_fields": REQUIRED,
        "realized_pnl_reconciliation_contract_present_fields": REQUIRED,
        "realized_pnl_reconciliation_contract_missing_fields": [],
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_map": pnl_map,
        "generic_supervised_paper_close_execution_map": {"dry_run_order_intent_payload": _dry_run_payload()},
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400, "strategy_signal_diagnostic_read": 1},
        "candidate_diagnostic_examples": [{"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY"}],
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "real_close_execution_available": False,
        "paper_open_position_available": False,
        "paper_position_open": False,
        "paper_position_closed": False,
        "paper_open_position_monitor_ready": False,
        "close_trigger_available": False,
        "paper_close_execution_ready": False,
        "generic_close_execution_allowed": False,
        "broker_close_allowed": False,
        "would_prepare_close": False,
        "would_call_paper_broker_close": False,
        "would_close": False,
        "would_reconcile_realized_pnl": False,
        "would_write_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_submit": False,
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_allowed": False,
        "generic_realized_pnl_reconciliation_allowed": False,
        "paper_realized_pnl_reconciliation_ready": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": False,
        "generic_realized_pnl_operator_gate_required": True,
        "generic_realized_pnl_operator_gate_satisfied": False,
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "paper_state_status_consistency": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "paper_state_modified_by_generic_realized_pnl_reconciliation_preflight": False,
        "paper_status_modified_by_generic_realized_pnl_reconciliation_preflight": False,
        "orders_submitted_by_generic_realized_pnl_reconciliation_preflight": 0,
        "positions_opened_by_generic_realized_pnl_reconciliation_preflight": 0,
        "positions_closed_by_generic_realized_pnl_reconciliation_preflight": 0,
        "broker_submit_called_by_generic_realized_pnl_reconciliation_preflight": False,
        "broker_close_called_by_generic_realized_pnl_reconciliation_preflight": False,
    }
    for key in FALSE_EXECUTION_KEYS:
        report[key] = False
    return report


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir="data")


def test_final_audit_preflight_ready_but_no_final_audit_without_realized_pnl_reconciliation(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight_report.json", _u34_report())

    report = run_generic_supervised_paper_final_audit_preflight(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_final_audit_preflight_ready"] is True
    assert report["generic_final_audit_preflight_ready"] is True
    assert report["paper_final_audit_preflight_ready"] is True
    assert report["final_audit_preflight_diagnostic_available"] is True
    assert report["final_audit_preflight_diagnostic_count"] == 401
    assert report["final_audit_contract_shape_modelable"] is True
    assert report["final_audit_contract_missing_fields"] == []
    assert report["generic_supervised_paper_realized_pnl_reconciliation_preflight_ready"] is True
    assert report["broker_submit_receipt_available"] is False
    assert report["broker_close_receipt_available"] is False
    assert report["real_close_execution_available"] is False
    assert report["paper_position_closed"] is False
    assert report["paper_realized_pnl_reconciliation_ready"] is False
    assert report["generic_realized_pnl_reconciliation_allowed"] is False
    assert report["generic_final_audit_execution_allowed"] is False
    assert report["paper_final_audit_ready"] is False
    assert report["would_run_final_audit"] is False
    assert report["would_run_postmortem"] is False
    assert report["orders_submitted_by_generic_final_audit_preflight"] == 0
    assert report["positions_closed_by_generic_final_audit_preflight"] == 0
    assert report["paper_state_modified_by_generic_final_audit_preflight"] is False
    assert report["paper_status_modified_by_generic_final_audit_preflight"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_final_audit_preflight_requires_upstream_realized_pnl_preflight_report(tmp_path):
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_final_audit_preflight(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "missing_upstream_reports" in report["blockers"]
    assert report["generic_supervised_paper_final_audit_preflight_ready"] is False
    assert report["final_audit_preflight_diagnostic_available"] is False
    assert report["generic_final_audit_execution_allowed"] is False
    assert report["would_run_final_audit"] is False


def test_final_audit_preflight_rejects_not_ready_upstream_report(tmp_path):
    _write_markers(tmp_path)
    upstream = _u34_report()
    upstream["decision"] = "NOT_READY"
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight_report.json", upstream)

    report = run_generic_supervised_paper_final_audit_preflight(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert "not_ready_upstream_reports" in report["blockers"]
    assert report["generic_final_audit_preflight_patch_ready"] is False
    assert report["generic_final_audit_execution_allowed"] is False


def test_final_audit_preflight_detects_operator_env_and_stays_keep_diagnostic(tmp_path, monkeypatch):
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight_report.json", _u34_report())
    monkeypatch.setenv("LSR_V2_GENERIC_FINAL_AUDIT_ENABLE", "1")

    report = run_generic_supervised_paper_final_audit_preflight(_settings(tmp_path))

    assert report["status"] == "KEEP_DIAGNOSTIC"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_final_audit_operator_gate_satisfied"] is False
    assert report["generic_final_audit_execution_allowed"] is False


def test_final_audit_preflight_writes_report_and_jsonl(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("LSR_V2"):
            monkeypatch.delenv(key, raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight_report.json", _u34_report())

    settings = _settings(tmp_path)
    report = run_generic_supervised_paper_final_audit_preflight(settings)

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_final_audit_preflight_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_final_audit_preflight.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == READY_DECISION
    assert saved["recommended_next_patch"] == "29.4.4u-36 — Generic LSR-v2 supervised paper final audit execution scaffold"
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[-1])["event_type"] == report["event_type"]
