from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_candidate_detection_audit import (
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_paper_only_candidate_detection_audit,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _write_source_markers(root: Path) -> None:
    files = {
        "trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.py":
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT\ncandidate_detection_sources\n",
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "# no-lsr-v2-engine-read-only-artifact-hook\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _readiness_payload(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_READY",
        "generic_candidate_detection_readiness_ready": True,
        "lifecycle_state": "FLAT_LOCKED",
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "paper_state_status_consistency": True,
        "generic_candidate_detection_readiness_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_generic_candidate_detection_readiness_preflight": 0,
        "positions_opened_by_generic_candidate_detection_readiness_preflight": 0,
        "positions_closed_by_generic_candidate_detection_readiness_preflight": 0,
        "paper_state_modified_by_generic_candidate_detection_readiness_preflight": False,
        "paper_status_modified_by_generic_candidate_detection_readiness_preflight": False,
    }
    payload.update(overrides)
    return payload


def _project(tmp_path: Path) -> Settings:
    _write_source_markers(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight_report.json",
        _readiness_payload(),
    )
    return Settings(project_root=tmp_path)


def test_candidate_detection_audit_passes_without_candidate_and_remains_fail_closed(tmp_path: Path) -> None:
    settings = _project(tmp_path)

    report = run_generic_paper_only_candidate_detection_audit(settings)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_candidate_detection_audit_ready"] is True
    assert report["candidate_detection_diagnostic_scan_executed"] is True
    assert report["candidate_detection_scan_executed"] is False
    assert report["candidate_detected_diagnostic"] is False
    assert report["generic_candidate_detection_allowed"] is False
    assert report["generic_route_execution_allowed"] is False
    assert report["generic_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_generic_candidate_detection_audit"] == 0
    assert report["positions_opened_by_generic_candidate_detection_audit"] == 0
    assert report["paper_state_modified_by_generic_candidate_detection_audit"] is False
    assert (tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_audit_report.json").exists()
    assert (tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_audit.jsonl").exists()


def test_candidate_detection_audit_reports_candidate_diagnostically_without_execution(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    _append_jsonl(
        tmp_path / "data" / "paper_events.jsonl",
        {
            "event_type": "GENERIC_LSR_V2_CANDIDATE_DETECTED_DIAGNOSTIC",
            "candidate_detected_diagnostic": True,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "cycle_id": "pc_test",
        },
    )

    report = run_generic_paper_only_candidate_detection_audit(settings)

    assert report["status"] == "PASS"
    assert report["candidate_detected_diagnostic"] is True
    assert report["candidate_detected_diagnostic_count"] == 1
    assert report["candidate_detection_source_counts"]["paper_events_jsonl_diagnostic_read"] == 1
    assert report["candidate_diagnostic_examples"][0]["symbol"] == "BTC/USDT"
    assert report["generic_route_execution_allowed"] is False
    assert report["generic_submit_execution_allowed"] is False
    assert report["broker_submit_called_by_generic_candidate_detection_audit"] is False


def test_candidate_detection_audit_warns_when_readiness_missing(tmp_path: Path) -> None:
    _write_source_markers(tmp_path)

    report = run_generic_paper_only_candidate_detection_audit(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "candidate_detection_readiness_report_present" in report["blockers"]
    assert report["generic_candidate_detection_allowed"] is False


def test_candidate_detection_audit_warns_when_readiness_execution_flag_not_fail_closed(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight_report.json",
        _readiness_payload(generic_submit_execution_allowed=True),
    )

    report = run_generic_paper_only_candidate_detection_audit(settings)

    assert report["status"] == "WARN"
    assert "execution_flags_fail_closed" in report["blockers"]
    assert report["generic_submit_execution_allowed"] is False


def test_candidate_detection_audit_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    settings = _project(tmp_path)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    report = run_generic_paper_only_candidate_detection_audit(settings)

    assert report["status"] == "WARN"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_candidate_detection_allowed"] is False
