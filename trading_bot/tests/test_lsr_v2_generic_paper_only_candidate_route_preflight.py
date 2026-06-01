from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_candidate_route_preflight import (
    READY_DECISION,
    Settings,
    run_generic_paper_only_candidate_route_preflight,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markers(root: Path) -> None:
    (root / "trading_bot/core").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_audit.py").write_text(
        "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT\ncandidate_detection_source_counts\n",
        encoding="utf-8",
    )
    (root / "trading_bot/core/paper_engine.py").write_text("class PaperTradingEngine: pass\n", encoding="utf-8")
    (root / "trading_bot/run_paper_trading.py").write_text(
        "# no-lsr-v2-engine-read-only-artifact-hook\n",
        encoding="utf-8",
    )


def _u17_report(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT_READY",
        "generic_candidate_detection_audit_ready": True,
        "candidate_detection_diagnostic_scan_executed": True,
        "candidate_detection_scan_executed": False,
        "candidate_detected_diagnostic": True,
        "candidate_detected_diagnostic_count": 401,
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
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "paper_state_status_consistency": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "paper_state_modified_by_generic_candidate_detection_audit": False,
        "paper_status_modified_by_generic_candidate_detection_audit": False,
        "orders_submitted_by_generic_candidate_detection_audit": 0,
        "positions_opened_by_generic_candidate_detection_audit": 0,
        "positions_closed_by_generic_candidate_detection_audit": 0,
        "generic_candidate_detection_audit_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
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


def test_route_preflight_passes_with_diagnostic_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_paper_only_candidate_detection_audit_report.json", _u17_report())

    report = run_generic_paper_only_candidate_route_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_candidate_route_preflight_ready"] is True
    assert report["candidate_route_preflight_diagnostic_available"] is True
    assert report["candidate_route_preflight_diagnostic_count"] == 401
    assert report["route_candidate_available"] is False
    assert report["paper_order_intent_ready"] is False
    assert report["would_route"] is False
    assert report["would_create_order"] is False
    assert report["would_submit"] is False
    assert report["generic_route_execution_allowed"] is False
    assert report["generic_order_intent_creation_allowed"] is False
    assert report["orders_submitted_by_generic_candidate_route_preflight"] == 0
    assert report["positions_opened_by_generic_candidate_route_preflight"] == 0
    assert report["paper_state_modified_by_generic_candidate_route_preflight"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_route_preflight_still_passes_without_diagnostic_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_candidate_detection_audit_report.json",
        _u17_report(candidate_detected_diagnostic=False, candidate_detected_diagnostic_count=0, candidate_detection_source_counts={}),
    )

    report = run_generic_paper_only_candidate_route_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "PASS"
    assert report["candidate_route_preflight_diagnostic_available"] is False
    assert report["candidate_route_preflight_diagnostic_count"] == 0
    assert report["route_candidate_available"] is False
    assert report["paper_order_intent_ready"] is False


def test_route_preflight_warns_when_upstream_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)

    report = run_generic_paper_only_candidate_route_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "candidate_detection_audit_report_present" in report["blockers"]
    assert report["generic_candidate_route_preflight_ready"] is False
    assert report["generic_route_execution_allowed"] is False


def test_route_preflight_warns_when_existing_route_candidate_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _write_markers(tmp_path)
    _write_json(
        tmp_path / "data/lsr_v2_generic_paper_only_candidate_detection_audit_report.json",
        _u17_report(route_candidate_available=True),
    )

    report = run_generic_paper_only_candidate_route_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "no_existing_route_candidate" in report["blockers"]
    assert report["route_candidate_available"] is False
    assert report["generic_route_execution_allowed"] is False


def test_route_preflight_warns_on_operator_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")
    _write_markers(tmp_path)
    _write_json(tmp_path / "data/lsr_v2_generic_paper_only_candidate_detection_audit_report.json", _u17_report())

    report = run_generic_paper_only_candidate_route_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert "operator_env_absent" in report["blockers"]
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["generic_submit_execution_allowed"] is False
