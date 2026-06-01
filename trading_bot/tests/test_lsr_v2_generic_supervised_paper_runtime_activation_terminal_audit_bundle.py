from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle import (
    BUNDLE_READY_DECISION,
    EXECUTION_READY_DECISION,
    PREFLIGHT_READY_DECISION,
    SCAFFOLD_READY_DECISION,
    Settings,
    run_generic_supervised_paper_runtime_activation_terminal_audit_bundle,
    run_generic_supervised_paper_runtime_activation_terminal_audit_execution,
    run_generic_supervised_paper_runtime_activation_terminal_audit_preflight,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markers(tmp_path: Path) -> None:
    core = tmp_path / "trading_bot/core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution.py").write_text(
        "GENERIC_LSR_V2_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION\n"
        "generic_runtime_activation_envelope_execution_ready\n",
        encoding="utf-8",
    )
    (core / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight.py").write_text(
        "run_generic_supervised_paper_runtime_activation_terminal_audit_preflight\n",
        encoding="utf-8",
    )
    (core / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold.py").write_text(
        "run_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold\n",
        encoding="utf-8",
    )
    (core / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution.py").write_text(
        "run_generic_supervised_paper_runtime_activation_terminal_audit_execution\n",
        encoding="utf-8",
    )
    (core / "paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (tmp_path / "trading_bot").mkdir(exist_ok=True)
    (tmp_path / "trading_bot/run_paper_trading.py").write_text("import argparse\n", encoding="utf-8")


def _u64_report() -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_READY",
        "generic_supervised_paper_runtime_activation_envelope_execution_ready": True,
        "generic_runtime_activation_envelope_execution_ready": True,
        "generic_runtime_activation_envelope_execution_model_ready": True,
        "generic_runtime_activation_envelope_execution_patch_ready": True,
        "generic_runtime_activation_envelope_execution_allowed": False,
        "generic_supervised_paper_runtime_activation_envelope_execution_map": {
            "mode": "generic_supervised_paper_runtime_activation_envelope_execution_controlled",
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
        "paper_runtime_activation_envelope_ready": False,
        "runtime_activation_envelope_runtime_executed": False,
        "terminal_ready_synthesis_runtime_executed": False,
    }


def _write_u64_report(tmp_path: Path, payload: dict | None = None) -> None:
    _write_json(
        tmp_path / "data/lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_report.json",
        payload if payload is not None else _u64_report(),
    )


def test_terminal_audit_bundle_runs_three_substeps_and_stays_fail_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u64_report(tmp_path)

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(_settings(tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == BUNDLE_READY_DECISION
    assert report["generic_supervised_paper_runtime_activation_terminal_audit_bundle_ready"] is True
    assert report["bundle_steps"]["preflight"]["decision"] == PREFLIGHT_READY_DECISION
    assert report["bundle_steps"]["execution_scaffold"]["decision"] == SCAFFOLD_READY_DECISION
    assert report["bundle_steps"]["execution"]["decision"] == EXECUTION_READY_DECISION
    assert report["generic_runtime_activation_terminal_audit_execution_allowed"] is False
    assert report["generic_integrated_operation_execution_allowed"] is False
    assert report["future_integrated_operation_allowed"] is False
    assert report["would_run_runtime_activation_terminal_audit"] is False
    assert report["would_run_integrated_operation"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False
    assert report["would_send_telegram"] is False
    assert report["would_start_scheduler"] is False
    assert report["all_execution_flags_fail_closed"] is True


def test_preflight_keeps_explicit_execution_patch_blocker(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u64_report(tmp_path)

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_preflight(_settings(tmp_path))
    gate = report["generic_supervised_paper_runtime_activation_terminal_audit_preflight_map"][
        "runtime_activation_terminal_audit_preflight_gate_model"
    ]

    assert report["decision"] == PREFLIGHT_READY_DECISION
    assert "explicit_runtime_activation_terminal_audit_execution_patch_required" in gate[
        "runtime_activation_terminal_audit_preflight_blocked_reasons"
    ]
    assert gate["runtime_activation_terminal_audit_runtime_executed"] is False
    assert gate["operator_runtime_activation_terminal_audit_gate_satisfied"] is False


def test_execution_removes_future_patch_blocker_but_requires_runtime_evidence(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u64_report(tmp_path)
    run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(_settings(tmp_path))

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_execution(_settings(tmp_path))
    gate = report["generic_supervised_paper_runtime_activation_terminal_audit_execution_map"][
        "runtime_activation_terminal_audit_execution_gate_model"
    ]

    assert report["decision"] == EXECUTION_READY_DECISION
    assert "explicit_runtime_activation_terminal_audit_execution_patch_required" not in gate[
        "runtime_activation_terminal_audit_execution_blocked_reasons"
    ]
    assert "runtime_activation_terminal_audit_runtime_absent" in gate[
        "runtime_activation_terminal_audit_execution_blocked_reasons"
    ]
    assert "broker_submit_receipt_absent" in gate["runtime_activation_terminal_audit_execution_blocked_reasons"]
    assert "broker_close_receipt_absent" in gate["runtime_activation_terminal_audit_execution_blocked_reasons"]
    assert gate["runtime_values_present"] is False


def test_missing_u64_upstream_fails_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert report["generic_runtime_activation_terminal_audit_execution_allowed"] is False
    assert report["would_submit"] is False
    assert report["would_close"] is False


def test_not_ready_u64_upstream_fails_closed(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    bad = _u64_report()
    bad["decision"] = "KEEP_DIAGNOSTIC"
    _write_u64_report(tmp_path, bad)

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(_settings(tmp_path))

    assert report["status"] == "FAIL"
    assert report["generic_integrated_operation_execution_allowed"] is False
    assert report["would_run_runtime_activation_terminal_audit"] is False


def test_reports_and_jsonl_are_written(tmp_path: Path) -> None:
    _write_markers(tmp_path)
    _write_u64_report(tmp_path)

    report = run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(_settings(tmp_path))

    expected = [
        "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight_report.json",
        "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_report.json",
        "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_report.json",
        "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle_report.json",
    ]
    for name in expected:
        assert (tmp_path / "data" / name).exists()
    saved = json.loads((tmp_path / "data/lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle_report.json").read_text(encoding="utf-8"))
    assert saved["decision"] == BUNDLE_READY_DECISION
    assert report["report"].endswith("lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle_report.json")
