from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution import (
    READY_DECISION,
    Settings,
    run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_markers(tmp_path: Path) -> None:
    marker_files = {
        "trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_scaffold.py": (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_HANDOFF_EXECUTION_SCAFFOLD\n"
            "generic_integrated_operation_final_readiness_audit_handoff_execution_scaffold_ready\n"
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


def _base_u57_report() -> dict:
    gate = {
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_gate_model_ready": True,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_model_ready": True,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_patch_ready": True,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_conditions_satisfied": False,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_allowed": False,
        "explicit_integrated_operation_final_readiness_audit_handoff_execution_patch_required": True,
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
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_HANDOFF_EXECUTION_SCAFFOLD_READY",
        "generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_scaffold_ready": True,
        "generic_integrated_operation_final_readiness_audit_handoff_execution_scaffold_ready": True,
        "generic_integrated_operation_final_readiness_audit_handoff_execution_scaffold_model_ready": True,
        "generic_integrated_operation_final_readiness_audit_handoff_execution_scaffold_patch_ready": True,
        "generic_integrated_operation_final_readiness_audit_handoff_execution_scaffold_allowed": False,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_diagnostic_available": True,
        "integrated_operation_final_readiness_audit_handoff_execution_scaffold_diagnostic_count": 401,
        "generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_scaffold_map": {
            "mode": "generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_scaffold_only",
            "read_only": True,
            "fail_closed": True,
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
            "integrated_operation_final_readiness_audit_handoff_execution_scaffold_gate_model": gate,
        },
        "candidate_detection_source_counts": {"paper_events_jsonl_diagnostic_read": 400},
        "candidate_diagnostic_examples": [
            {"event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT", "symbol": "BTC/USDT"}
        ],
        "lifecycle_state": "FLAT_LOCKED",
        "lifecycle_state_complete": False,
        "future_integrated_operation_allowed": False,
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
    }


def _write_u57_report(tmp_path: Path, payload: dict | None = None) -> None:
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_scaffold_report.json",
        payload if payload is not None else _base_u57_report(),
    )


def test_integrated_operation_final_readiness_audit_handoff_execution_ready_but_fail_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u57_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_ready"] is True
    assert report["generic_integrated_operation_final_readiness_audit_handoff_execution_model_ready"] is True
    assert report["generic_integrated_operation_final_readiness_audit_handoff_execution_patch_ready"] is True
    assert report["paper_integrated_operation_final_readiness_audit_handoff_execution_ready"] is True
    assert report["generic_integrated_operation_final_readiness_audit_handoff_execution_allowed"] is False
    assert report["generic_integrated_operation_execution_allowed"] is False
    assert report["future_integrated_operation_allowed"] is False
    assert report["would_run_integrated_operation_final_readiness_audit_handoff"] is False
    assert report["would_run_integrated_operation"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False
    assert report["all_execution_flags_fail_closed"] is True


def test_gate_model_removes_future_handoff_execution_patch_blocker_but_requires_runtime_evidence(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u57_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))
    gate = report["generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_map"][
        "integrated_operation_final_readiness_audit_handoff_execution_gate_model"
    ]

    assert gate["integrated_operation_final_readiness_audit_handoff_execution_gate_model_ready"] is True
    assert gate["integrated_operation_final_readiness_audit_handoff_execution_allowed"] is False
    assert "explicit_integrated_operation_final_readiness_audit_handoff_execution_patch_required" not in gate
    assert "explicit_integrated_operation_final_readiness_audit_handoff_execution_patch_required" not in gate[
        "integrated_operation_final_readiness_audit_handoff_execution_blocked_reasons"
    ]
    assert "broker_submit_receipt_absent" in gate["integrated_operation_final_readiness_audit_handoff_execution_blocked_reasons"]
    assert "runtime_values_absent_or_deferred" in gate["integrated_operation_final_readiness_audit_handoff_execution_blocked_reasons"]
    assert "operator_integrated_operation_final_readiness_audit_handoff_gate_not_satisfied" in gate[
        "integrated_operation_final_readiness_audit_handoff_execution_blocked_reasons"
    ]
    assert gate["runtime_values_present"] is False


def test_missing_upstream_report_fails_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert "missing_upstream_reports" in report["blockers"]
    assert report["would_run_integrated_operation_final_readiness_audit_handoff"] is False
    assert report["generic_integrated_operation_execution_allowed"] is False


def test_not_ready_upstream_report_fails_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    bad = _base_u57_report()
    bad["decision"] = "KEEP_DIAGNOSTIC"
    _write_u57_report(tmp_path, bad)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert "not_ready_upstream_reports" in report["blockers"]
    assert report["would_submit"] is False
    assert report["would_close"] is False


def test_missing_source_markers_fails_closed(tmp_path: Path) -> None:
    _write_u57_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert "missing_source_markers" in report["blockers"]
    assert report["generic_paper_state_mutation_allowed"] is False
    assert report["generic_paper_status_mutation_allowed"] is False


def test_report_and_jsonl_are_written(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u57_report(tmp_path)

    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution(_settings(tmp_path))

    report_path = tmp_path / "data/lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_report.json"
    jsonl_path = tmp_path / "data/lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution.jsonl"
    assert report_path.exists()
    assert jsonl_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["decision"] == READY_DECISION
    assert json.loads(jsonl_path.read_text(encoding="utf-8").strip())["decision"] == READY_DECISION
    assert report["report"].endswith("lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_execution_report.json")
