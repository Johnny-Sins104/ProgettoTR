from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_submit_readiness_preflight import (
    READY_DECISION,
    REQUIRED_ORDER_INTENT_FIELDS,
    Settings,
    run_generic_paper_only_submit_readiness_preflight,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markers(root: Path) -> None:
    (root / "trading_bot/core").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/core/lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py").write_text(
        "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN\n"
        "paper_order_intent_materialization_dry_run_ready\n",
        encoding="utf-8",
    )
    (root / "trading_bot/core/paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _dry_run_payload(**overrides: object) -> dict:
    payload = {
        "symbol": "deferred_until_explicit_order_intent_patch",
        "side": "deferred_until_explicit_order_intent_patch",
        "entry_price": "deferred_until_explicit_order_intent_patch",
        "stop_loss": "deferred_until_explicit_order_intent_patch",
        "take_profit": "deferred_until_explicit_order_intent_patch",
        "risk_amount": "deferred_until_explicit_order_intent_patch",
        "position_size": "deferred_until_explicit_order_intent_patch",
        "max_open_positions": 1,
        "paper_only": True,
        "materialized": False,
        "persisted": False,
        "dry_run_only": True,
        "runtime_values_present": False,
    }
    payload.update(overrides)
    return payload


def _u23_report(**overrides: object) -> dict:
    required = list(REQUIRED_ORDER_INTENT_FIELDS)
    payload = overrides.pop("dry_run_payload", _dry_run_payload())
    report = {
        "prompt": "29.4.4u-23",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_READY",
        "generic_order_intent_materialization_dry_run_ready": True,
        "generic_order_intent_materialization_dry_run_map_ready": True,
        "order_intent_validation_preflight_ready": True,
        "paper_order_intent_contract_ready": True,
        "paper_order_intent_contract_validatable": True,
        "paper_order_intent_contract_validation_preflight_ready": True,
        "paper_order_intent_dry_run_ready": True,
        "paper_order_intent_materialization_dry_run_ready": True,
        "paper_order_intent_materialization_simulated": True,
        "would_materialize_order_intent_dry_run": True,
        "order_intent_candidate_audit_diagnostic_available": True,
        "order_intent_candidate_audit_diagnostic_count": 401,
        "candidate_detection_source_counts": {
            "paper_events_jsonl_diagnostic_read": 400,
            "strategy_signal_diagnostic_read": 1,
        },
        "candidate_diagnostic_examples": [
            {"cycle_id": "pc_fixture", "symbol": "BTC/USDT", "side": "BUY", "route_candidate_available": False}
        ],
        "order_intent_candidate_contract_required_fields": required,
        "order_intent_candidate_contract_present_fields": required,
        "order_intent_candidate_contract_missing_fields": [],
        "generic_order_intent_materialization_dry_run_map": {
            "dry_run_order_intent_payload": payload,
            "contract_ready_for_dry_run_materialization": True,
            "paper_order_intent_materialization_dry_run_ready": True,
            "paper_order_intent_materialization_simulated": True,
            "paper_order_intent_runtime_values_present": False,
        },
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "would_validate_order_intent": False,
        "would_create_order_intent": False,
        "would_create_order": False,
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
        "paper_state_modified_by_generic_order_intent_materialization_dry_run": False,
        "paper_status_modified_by_generic_order_intent_materialization_dry_run": False,
        "orders_submitted_by_generic_order_intent_materialization_dry_run": 0,
        "positions_opened_by_generic_order_intent_materialization_dry_run": 0,
        "positions_closed_by_generic_order_intent_materialization_dry_run": 0,
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


def test_submit_readiness_preflight_passes_with_u23_materialization_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(),
    )

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_submit_readiness_preflight_ready"] is True
    assert report["paper_submit_readiness_preflight_ready"] is True
    assert report["generic_submit_operator_gate_required"] is True
    assert report["generic_submit_operator_gate_satisfied"] is False
    assert report["paper_order_intent_dry_run_ready"] is True
    assert report["paper_order_intent_runtime_values_present"] is False
    assert report["paper_order_intent_ready"] is False
    assert report["paper_submit_candidate_ready"] is False
    assert report["paper_submit_execution_ready"] is False
    assert report["generic_submit_execution_allowed"] is False
    assert report["would_submit"] is False
    assert report["would_call_paper_broker_submit"] is False
    assert report["orders_submitted_by_generic_submit_readiness_preflight"] == 0
    assert report["positions_opened_by_generic_submit_readiness_preflight"] == 0
    assert report["paper_state_modified_by_generic_submit_readiness_preflight"] is False
    assert report["paper_status_modified_by_generic_submit_readiness_preflight"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_submit_readiness_preflight_warns_when_upstream_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_materialization_dry_run_report_present" in report["blockers"]
    assert report["generic_submit_readiness_preflight_ready"] is False
    assert report["would_submit"] is False


def test_submit_readiness_preflight_warns_when_dry_run_not_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(paper_order_intent_dry_run_ready=False, paper_order_intent_materialization_dry_run_ready=False),
    )

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "dry_run_order_intent_ready" in report["blockers"]
    assert "materialization_dry_run_ready" in report["blockers"]
    assert report["paper_submit_candidate_ready"] is False


def test_submit_readiness_preflight_warns_when_contract_policy_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(dry_run_payload=_dry_run_payload(max_open_positions=2, paper_only=False)),
    )

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "submit_readiness_contract_ready" in report["blockers"]
    assert "single_position_policy_ready" in report["blockers"]
    assert "paper_only_policy_ready" in report["blockers"]
    assert report["generic_submit_readiness_preflight_map"]["submit_gate_model"]["max_open_positions_valid"] is False
    assert report["would_submit"] is False


def test_submit_readiness_preflight_warns_when_submit_unblocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(generic_submit_execution_allowed=True),
    )

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "submit_execution_blocked" in report["blockers"]
    assert "execution_flags_fail_closed" in report["blockers"]
    assert report["generic_submit_execution_allowed"] is False
    assert report["would_call_paper_broker_submit"] is False


def test_submit_readiness_preflight_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_SUBMIT_ENABLE", "1")
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(),
    )

    report = run_generic_paper_only_submit_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_submit_operator_gate_satisfied"] is False
    assert report["would_submit"] is False


def test_submit_readiness_preflight_writes_report_and_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_SUBMIT_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json",
        _u23_report(),
    )

    settings = Settings(project_root=tmp_path)
    report = run_generic_paper_only_submit_readiness_preflight(settings)

    report_path = tmp_path / "data/lsr_v2_generic_paper_only_submit_readiness_preflight_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_paper_only_submit_readiness_preflight.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == READY_DECISION
    assert report["generic_submit_readiness_preflight_map"]["submit_gate_model"]["operator_gate_required"] is True
