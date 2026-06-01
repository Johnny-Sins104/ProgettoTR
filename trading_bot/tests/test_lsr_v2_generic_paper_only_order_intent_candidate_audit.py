from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_order_intent_candidate_audit import (
    READY_DECISION,
    Settings,
    run_generic_paper_only_order_intent_candidate_audit,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markers(root: Path) -> None:
    (root / "trading_bot/core").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/core/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py").write_text(
        "GENERIC_LSR_V2_PAPER_ONLY_HANDOFF_TO_ORDER_INTENT_DRY_RUN_PREFLIGHT\n"
        "order_intent_dry_run_preflight_diagnostic_count\n",
        encoding="utf-8",
    )
    (root / "trading_bot/core/paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _u20_report(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ONLY_HANDOFF_TO_ORDER_INTENT_DRY_RUN_PREFLIGHT_READY",
        "generic_handoff_to_order_intent_dry_run_preflight_ready": True,
        "order_intent_dry_run_preflight_diagnostic_available": True,
        "order_intent_dry_run_preflight_diagnostic_count": 401,
        "candidate_detection_source_counts": {
            "paper_events_jsonl_diagnostic_read": 400,
            "strategy_signal_diagnostic_read": 1,
        },
        "candidate_diagnostic_examples": [
            {
                "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "route_candidate_available": False,
                "paper_order_intent_ready": False,
            }
        ],
        "handoff_to_order_intent_dry_run_preflight_map": {
            "order_intent_dry_run_context": {
                "diagnostic_handoff_context_available": True,
                "route_candidate_available": False,
                "handoff_candidate_available": False,
                "paper_order_intent_ready": False,
                "paper_order_intent_dry_run_ready": False,
                "would_create_order_intent": False,
                "would_create_order": False,
                "would_submit": False,
                "blocked_reason": "order_intent_creation_not_allowed_dry_run_preflight_only",
            },
            "paper_order_intent_model": {
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
            },
        },
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_dry_run_ready": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_submit": False,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "paper_state_status_consistency": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "paper_state_modified_by_generic_handoff_to_order_intent_dry_run_preflight": False,
        "paper_status_modified_by_generic_handoff_to_order_intent_dry_run_preflight": False,
        "orders_submitted_by_generic_handoff_to_order_intent_dry_run_preflight": 0,
        "positions_opened_by_generic_handoff_to_order_intent_dry_run_preflight": 0,
        "positions_closed_by_generic_handoff_to_order_intent_dry_run_preflight": 0,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_candidate_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
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


def test_order_intent_candidate_audit_passes_with_dry_run_diagnostics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json",
        _u20_report(),
    )

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_order_intent_candidate_audit_ready"] is True
    assert report["order_intent_candidate_audit_diagnostic_available"] is True
    assert report["order_intent_candidate_audit_diagnostic_count"] == 401
    assert report["order_intent_candidate_contract_shape_modelable"] is True
    assert report["paper_order_intent_candidate_ready"] is False
    assert report["paper_order_intent_ready"] is False
    assert report["paper_order_intent_materialized"] is False
    assert report["paper_order_intent_persisted"] is False
    assert report["would_create_order_intent"] is False
    assert report["would_submit"] is False
    assert report["generic_order_intent_candidate_materialization_allowed"] is False
    assert report["generic_order_intent_validation_allowed"] is False
    assert report["generic_order_intent_creation_allowed"] is False
    assert report["generic_order_intent_persistence_allowed"] is False
    assert report["orders_submitted_by_generic_order_intent_candidate_audit"] == 0
    assert report["positions_opened_by_generic_order_intent_candidate_audit"] == 0
    assert report["paper_state_modified_by_generic_order_intent_candidate_audit"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_order_intent_candidate_audit_warns_when_upstream_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "handoff_to_order_intent_dry_run_preflight_report_present" in report["blockers"]
    assert report["generic_order_intent_candidate_audit_ready"] is False
    assert report["generic_order_intent_creation_allowed"] is False
    assert report["paper_order_intent_candidate_ready"] is False


def test_order_intent_candidate_audit_warns_without_diagnostic_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json",
        _u20_report(order_intent_dry_run_preflight_diagnostic_available=False, order_intent_dry_run_preflight_diagnostic_count=0),
    )

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_dry_run_preflight_diagnostic_available" in report["blockers"]
    assert report["order_intent_candidate_audit_diagnostic_available"] is False
    assert report["paper_order_intent_ready"] is False


def test_order_intent_candidate_audit_warns_when_order_intent_already_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json",
        _u20_report(paper_order_intent_ready=True),
    )

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "no_existing_paper_order_intent" in report["blockers"]
    assert report["paper_order_intent_ready"] is False
    assert report["generic_submit_execution_allowed"] is False


def test_order_intent_candidate_audit_warns_when_creation_is_unblocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json",
        _u20_report(generic_order_intent_creation_allowed=True),
    )

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "order_intent_creation_blocked" in report["blockers"]
    assert "execution_flags_fail_closed" in report["blockers"]
    assert report["generic_order_intent_creation_allowed"] is False
    assert report["would_create_order_intent"] is False


def test_order_intent_candidate_audit_warns_on_operator_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json",
        _u20_report(),
    )

    report = run_generic_paper_only_order_intent_candidate_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_order_intent_creation_allowed"] is False
