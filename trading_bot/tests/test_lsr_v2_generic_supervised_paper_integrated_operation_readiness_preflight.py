from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_generic_supervised_paper_integrated_operation_readiness_preflight import (
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_integrated_operation_readiness_preflight,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markers(tmp_path: Path) -> None:
    marker_files = {
        "trading_bot/core/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution.py": (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION\n"
            "generic_terminal_lifecycle_handoff_execution_ready\n"
        ),
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "import argparse\n",
    }
    for rel, text in marker_files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path)


def _base_u49_report() -> dict:
    gate = {
        "terminal_lifecycle_handoff_execution_gate_model_ready": True,
        "terminal_lifecycle_handoff_execution_model_ready": True,
        "terminal_lifecycle_handoff_execution_conditions_satisfied": False,
        "terminal_lifecycle_handoff_execution_allowed": False,
        "runtime_values_present": False,
        "required_model_fields": [
            "symbol", "side", "entry_price", "stop_loss", "take_profit",
            "risk_amount", "position_size", "max_open_positions", "paper_only",
        ],
        "present_model_fields": [
            "symbol", "side", "entry_price", "stop_loss", "take_profit",
            "risk_amount", "position_size", "max_open_positions", "paper_only",
        ],
    }
    return {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_READY",
        "generic_supervised_paper_terminal_lifecycle_handoff_execution_ready": True,
        "generic_terminal_lifecycle_handoff_execution_ready": True,
        "generic_terminal_lifecycle_handoff_execution_model_ready": True,
        "generic_terminal_lifecycle_handoff_execution_patch_ready": True,
        "terminal_lifecycle_handoff_execution_diagnostic_available": True,
        "terminal_lifecycle_handoff_execution_diagnostic_count": 401,
        "generic_supervised_paper_terminal_lifecycle_handoff_execution_map": {
            "dry_run_order_intent_payload": {
                "symbol": "deferred_until_explicit_order_intent_patch",
                "side": "deferred_until_explicit_order_intent_patch",
                "entry_price": "deferred_until_explicit_order_intent_patch",
                "stop_loss": "deferred_until_explicit_order_intent_patch",
                "take_profit": "deferred_until_explicit_order_intent_patch",
                "risk_amount": "deferred_until_explicit_order_intent_patch",
                "position_size": "deferred_until_explicit_order_intent_patch",
                "max_open_positions": 1,
                "paper_only": True,
                "dry_run_only": True,
                "materialized": False,
                "persisted": False,
                "runtime_values_present": False,
            },
            "terminal_lifecycle_handoff_execution_gate_model": gate,
        },
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "real_close_execution_available": False,
        "paper_position_closed": False,
        "paper_realized_pnl_reconciliation_ready": False,
        "realized_pnl_written": False,
        "paper_final_audit_ready": False,
        "paper_postmortem_ready": False,
        "paper_lifecycle_completion_ready": False,
        "paper_lifecycle_state_status_completion_mutation_ready": False,
        "paper_terminal_lifecycle_handoff_ready": False,
        "final_audit_runtime_executed": False,
        "postmortem_runtime_executed": False,
        "lifecycle_completion_audit_runtime_executed": False,
        "lifecycle_state_status_completion_mutation_runtime_executed": False,
        "terminal_lifecycle_handoff_runtime_executed": False,
        "scheduler_completion_handoff_runtime_executed": False,
        "telegram_lifecycle_completion_send_runtime_executed": False,
        "paper_state_terminal_handoff_mutated": False,
        "paper_status_terminal_handoff_mutated": False,
        "lifecycle_state": "FLAT_LOCKED",
        "lifecycle_state_complete": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400, "strategy_signal_diagnostic_read": 1},
        "candidate_diagnostic_examples": [{"symbol": "BTC/USDT", "side": "BUY", "candidate_detected_diagnostic": False}],
    }


def _seed_u49_report(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_report.json",
        _base_u49_report(),
    )


def test_integrated_operation_readiness_preflight_ready_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE", raising=False)
    _write_markers(tmp_path)
    _seed_u49_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_readiness_preflight(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_integrated_operation_readiness_preflight_ready"] is True
    assert report["generic_integrated_operation_readiness_preflight_model_ready"] is True
    assert report["generic_integrated_operation_readiness_preflight_patch_ready"] is True
    assert report["generic_integrated_operation_allowed"] is False
    assert report["future_integrated_operation_allowed"] is False
    assert report["paper_integrated_operation_ready"] is False
    assert report["would_run_integrated_operation"] is False
    assert report["would_handoff_terminal_lifecycle"] is False
    assert report["would_mutate_paper_state"] is False
    assert report["would_mutate_paper_status"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False
    assert report["all_execution_flags_fail_closed"] is True
    assert report["read_only_verified"] is True
    assert report["broker_submit_called_by_generic_integrated_operation_readiness_preflight"] is False
    assert report["broker_close_called_by_generic_integrated_operation_readiness_preflight"] is False


def test_integrated_operation_readiness_preflight_gate_lists_runtime_blockers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE", raising=False)
    _write_markers(tmp_path)
    _seed_u49_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_readiness_preflight(_settings(tmp_path))
    gate = report["generic_supervised_paper_integrated_operation_readiness_preflight_map"][
        "integrated_operation_readiness_preflight_gate_model"
    ]

    assert gate["integrated_operation_readiness_preflight_gate_model_ready"] is True
    assert gate["integrated_operation_readiness_preflight_conditions_satisfied"] is False
    assert gate["integrated_operation_execution_allowed"] is False
    assert "terminal_lifecycle_handoff_execution_not_allowed" in gate["integrated_operation_blocked_reasons"]
    assert "terminal_lifecycle_handoff_runtime_absent" in gate["integrated_operation_blocked_reasons"]
    assert "broker_submit_receipt_absent" in gate["integrated_operation_blocked_reasons"]
    assert "operator_integrated_operation_gate_not_satisfied" in gate["integrated_operation_blocked_reasons"]
    assert "explicit_integrated_operation_execution_patch_required" in gate["integrated_operation_blocked_reasons"]


def test_integrated_operation_readiness_preflight_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE", raising=False)
    _write_markers(tmp_path)
    _seed_u49_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_readiness_preflight(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_integrated_operation_readiness_preflight_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_integrated_operation_readiness_preflight.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == report["decision"]
    assert jsonl_path.read_text(encoding="utf-8").strip()


def test_integrated_operation_operator_env_does_not_unlock_without_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE", "1")
    monkeypatch.setenv(
        "LSR_V2_GENERIC_INTEGRATED_OPERATION_CONFIRMATION",
        "I_UNDERSTAND_GENERIC_PAPER_INTEGRATED_OPERATION_ONLY",
    )
    _write_markers(tmp_path)
    _seed_u49_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_readiness_preflight(_settings(tmp_path))
    gate = report["generic_supervised_paper_integrated_operation_readiness_preflight_map"][
        "integrated_operation_readiness_preflight_gate_model"
    ]

    assert gate["operator_integrated_operation_gate_satisfied"] is True
    assert gate["integrated_operation_execution_allowed"] is False
    assert report["generic_integrated_operation_allowed"] is False
    assert report["would_run_integrated_operation"] is False


def test_integrated_operation_readiness_preflight_contract_shape_modelable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE", raising=False)
    _write_markers(tmp_path)
    _seed_u49_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_readiness_preflight(_settings(tmp_path))

    assert report["integrated_operation_readiness_preflight_contract_required_fields"] == [
        "symbol", "side", "entry_price", "stop_loss", "take_profit",
        "risk_amount", "position_size", "max_open_positions", "paper_only",
    ]
    assert report["integrated_operation_readiness_preflight_contract_present_fields"] == report[
        "integrated_operation_readiness_preflight_contract_required_fields"
    ]
    assert report["integrated_operation_readiness_preflight_contract_missing_fields"] == []
    assert report["integrated_operation_readiness_preflight_contract_shape_modelable"] is True
