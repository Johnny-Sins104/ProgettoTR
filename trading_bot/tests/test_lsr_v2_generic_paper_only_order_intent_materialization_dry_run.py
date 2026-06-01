from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_order_intent_materialization_dry_run import (
    READY_DECISION,
    REQUIRED_ORDER_INTENT_FIELDS,
    Settings,
    run_generic_paper_only_order_intent_materialization_dry_run,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markers(root: Path) -> None:
    (root / "trading_bot/core").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/core/lsr_v2_generic_paper_only_order_intent_validation_preflight.py").write_text(
        "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT\n"
        "paper_order_intent_contract_validatable\n",
        encoding="utf-8",
    )
    (root / "trading_bot/core/paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _model(**overrides: object) -> dict:
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
    }
    payload.update(overrides)
    return payload


def _u22_report(**overrides: object) -> dict:
    required = list(REQUIRED_ORDER_INTENT_FIELDS)
    model = overrides.pop("model", _model())
    payload = {
        "prompt": "29.4.4u-22",
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_READY",
        "generic_order_intent_validation_preflight_ready": True,
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
        "order_intent_candidate_contract_required_fields": required,
        "order_intent_candidate_contract_present_fields": required,
        "order_intent_candidate_contract_missing_fields": [],
        "order_intent_validation_preflight_map": {
            "source_order_intent_model": model,
            "contract_shape_ready": True,
            "contract_value_validation_preflight_ready": True,
            "order_intent_validation_preflight_context": {
                "paper_order_intent_contract_ready": True,
                "paper_order_intent_validated": False,
                "paper_order_intent_materialized": False,
                "paper_order_intent_persisted": False,
                "paper_order_intent_ready": False,
                "would_validate_order_intent": False,
                "would_create_order_intent": False,
                "would_create_order": False,
                "would_submit": False,
            },
        },
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_dry_run_ready": False,
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
        "paper_state_modified_by_generic_order_intent_validation_preflight": False,
        "paper_status_modified_by_generic_order_intent_validation_preflight": False,
        "orders_submitted_by_generic_order_intent_validation_preflight": 0,
        "positions_opened_by_generic_order_intent_validation_preflight": 0,
        "positions_closed_by_generic_order_intent_validation_preflight": 0,
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
    payload.update(overrides)
    return payload


def test_order_intent_materialization_dry_run_passes_with_u22_validation_preflight(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(),
    )

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_order_intent_materialization_dry_run_ready"] is True
    assert report["paper_order_intent_dry_run_ready"] is True
    assert report["paper_order_intent_materialization_dry_run_ready"] is True
    assert report["paper_order_intent_materialization_simulated"] is True
    assert report["would_materialize_order_intent_dry_run"] is True
    assert report["paper_order_intent_runtime_values_present"] is False
    assert report["paper_order_intent_validated"] is False
    assert report["paper_order_intent_materialized"] is False
    assert report["paper_order_intent_persisted"] is False
    assert report["paper_order_intent_ready"] is False
    assert report["would_validate_order_intent"] is False
    assert report["would_create_order_intent"] is False
    assert report["would_submit"] is False
    assert report["generic_order_intent_materialization_allowed"] is False
    assert report["generic_order_intent_creation_allowed"] is False
    assert report["generic_order_intent_persistence_allowed"] is False
    assert report["generic_submit_execution_allowed"] is False
    assert report["orders_submitted_by_generic_order_intent_materialization_dry_run"] == 0
    assert report["positions_opened_by_generic_order_intent_materialization_dry_run"] == 0
    assert report["paper_state_modified_by_generic_order_intent_materialization_dry_run"] is False
    assert report["paper_status_modified_by_generic_order_intent_materialization_dry_run"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_order_intent_materialization_dry_run_warns_when_upstream_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_validation_preflight_report_present" in report["blockers"]
    assert report["generic_order_intent_materialization_dry_run_ready"] is False
    assert report["would_create_order_intent"] is False


def test_order_intent_materialization_dry_run_warns_when_contract_not_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field != "take_profit"]
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(
            paper_order_intent_contract_ready=False,
            paper_order_intent_contract_validatable=False,
            order_intent_candidate_contract_present_fields=fields,
            order_intent_candidate_contract_missing_fields=["take_profit"],
            model=_model(),
        ),
    )

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "contract_ready" in report["blockers"]
    assert "contract_validatable" in report["blockers"]
    assert report["paper_order_intent_dry_run_ready"] is False
    assert report["would_submit"] is False


def test_order_intent_materialization_dry_run_warns_when_real_materialization_already_happened(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(paper_order_intent_materialized=True, paper_order_intent_persisted=True),
    )

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_not_materialized" in report["blockers"]
    assert "order_intent_not_persisted" in report["blockers"]
    assert report["paper_order_intent_materialized"] is False
    assert report["paper_order_intent_persisted"] is False


def test_order_intent_materialization_dry_run_warns_when_creation_or_submit_unblocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(generic_order_intent_creation_allowed=True, generic_submit_execution_allowed=True),
    )

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_creation_blocked" in report["blockers"]
    assert "submit_execution_blocked" in report["blockers"]
    assert "execution_flags_fail_closed" in report["blockers"]
    assert report["would_create_order_intent"] is False


def test_order_intent_materialization_dry_run_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(),
    )

    report = run_generic_paper_only_order_intent_materialization_dry_run(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_order_intent_materialization_allowed"] is False


def test_order_intent_materialization_dry_run_writes_report_and_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json",
        _u22_report(),
    )

    settings = Settings(project_root=tmp_path)
    report = run_generic_paper_only_order_intent_materialization_dry_run(settings)

    report_path = tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_paper_only_order_intent_materialization_dry_run.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == READY_DECISION
    assert report["generic_order_intent_materialization_dry_run_map"]["dry_run_order_intent_payload"]["dry_run_only"] is True
