from __future__ import annotations

from pathlib import Path
import json

from core.lsr_v2_fourth_trade_route_preflight import (
    PASS_DECISION,
    build_lsr_v2_fourth_trade_route_preflight_report,
    build_lsr_v2_fourth_trade_route_preflight_report_from_files,
)


def _base_report(decision: str, **extra):
    payload = {"status": "PASS", "decision": decision}
    payload.update(extra)
    return payload


def _reports(*, fourth_candidate: bool = False, live: bool = False):
    return {
        "candidate_detection_audit": _base_report(
            "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY",
            candidate_detection_audit_ready=True,
            candidate_detected_diagnostic=True,
            candidate_detected_diagnostic_count=8,
            fourth_trade_candidate_detected_diagnostic=fourth_candidate,
            fourth_trade_candidate_detected_diagnostic_count=1 if fourth_candidate else 0,
            candidate_detection_latest_candidate={
                "cycle_id": "pc_test",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "event_type": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTED",
                "trade_ordinal": 4,
            },
            fourth_trade_locked=True,
            stability_lock_active=True,
            live_enabled=live,
        ),
        "unlock_activation_candidate_preflight": _base_report(
            "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY",
            unlock_activation_candidate_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "unlock_activation_preflight": _base_report(
            "LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY",
            operator_unlock_activation_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "unlock_draft": _base_report(
            "LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY",
            operator_unlock_draft_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "operator_gate": _base_report(
            "LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY",
            operator_rearm_gate_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "rearm_readiness": _base_report(
            "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY",
            rearm_readiness_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "candidate_hook": _base_report(
            "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY",
            candidate_lifecycle_hook_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "handoff": _base_report(
            "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY",
            read_only_handoff_preflight_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "parity": _base_report(
            "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY",
            visibility_parity_audit_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "engine_hook": _base_report(
            "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
            engine_artifact_hook_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "lifecycle": _base_report(
            "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
            lifecycle_auto_monitor_ready=True,
            lifecycle_state="FLAT_LOCKED",
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "dashboard": _base_report(
            "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
            dashboard_ready=True,
            visual_sl_tp_progress_bar_ready=True,
            visual_sl_tp_progress_bar="SL ================● TP",
            telegram_payload_ready=True,
            telegram_update_ready=True,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
        "postmortem": _base_report(
            "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
            three_trade_postmortem_complete=True,
            aggregate_realized_pnl=23.75,
            fourth_trade_locked=True,
            stability_lock_active=True,
        ),
    }


def test_route_preflight_passes_without_fourth_candidate_and_does_not_route():
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports=_reports(fourth_candidate=False),
        paper_state={"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75},
        paper_status={"open_positions": 0, "pending_orders": 0},
        source_audit={"route_preflight_required_markers_present": True},
        env={"operator_env_absent": True, "route_preflight_operator_env_currently_active": False},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["route_preflight_ready"] is True
    assert report["route_candidate_available"] is False
    assert report["would_route"] is False
    assert report["would_submit"] is False
    assert report["route_blocked_reason"] == "no_fourth_specific_candidate"
    assert report["candidate_routing_execution_allowed"] is False
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_route_preflight"] == 0
    assert report["positions_opened_by_route_preflight"] == 0
    assert report["paper_state_modified_by_route_preflight"] is False


def test_route_preflight_can_mark_would_route_diagnostic_for_fourth_candidate_only():
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports=_reports(fourth_candidate=True),
        paper_state={"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75},
        paper_status={"open_positions": 0, "pending_orders": 0},
        source_audit={"route_preflight_required_markers_present": True},
        env={"operator_env_absent": True, "route_preflight_operator_env_currently_active": False},
    )
    assert report["status"] == "PASS"
    assert report["would_route"] is True
    assert report["would_submit"] is False
    assert report["route_candidate"]["trade_ordinal"] == 4
    assert report["candidate_routing_execution_allowed"] is False
    assert report["candidate_submit_execution_allowed"] is False


def test_route_preflight_fails_closed_if_live_enabled():
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports=_reports(live=True),
        paper_state={"positions": {}, "orders": {}},
        paper_status={"open_positions": 0, "pending_orders": 0},
        source_audit={"route_preflight_required_markers_present": True},
        env={"operator_env_absent": True, "route_preflight_operator_env_currently_active": False},
    )
    assert report["status"] == "FAIL"
    assert "live_enabled" in report["blockers"]
    assert report["candidate_routing_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False


def test_route_preflight_warns_on_operator_env():
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports=_reports(),
        paper_state={"positions": {}, "orders": {}},
        paper_status={"open_positions": 0, "pending_orders": 0},
        source_audit={"route_preflight_required_markers_present": True},
        env={"operator_env_absent": False, "route_preflight_operator_env_currently_active": True},
    )
    assert report["status"] == "WARN"
    assert "operator_env_active_for_route_preflight" in report["blockers"]
    assert report["candidate_routing_execution_allowed"] is False


def test_route_preflight_from_files_writes_only_own_report(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    mapping = {
        "lsr_v2_fourth_trade_candidate_detection_audit_report.json": _reports()["candidate_detection_audit"],
        "lsr_v2_fourth_trade_unlock_activation_candidate_preflight_report.json": _reports()["unlock_activation_candidate_preflight"],
        "lsr_v2_fourth_trade_operator_unlock_activation_preflight_report.json": _reports()["unlock_activation_preflight"],
        "lsr_v2_fourth_trade_operator_unlock_draft_report.json": _reports()["unlock_draft"],
        "lsr_v2_fourth_trade_operator_rearm_gate_preflight_report.json": _reports()["operator_gate"],
        "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json": _reports()["rearm_readiness"],
        "lsr_v2_candidate_lifecycle_hook_preflight_report.json": _reports()["candidate_hook"],
        "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json": _reports()["handoff"],
        "lsr_v2_launcher_runner_visibility_parity_audit_report.json": _reports()["parity"],
        "lsr_v2_engine_read_only_artifact_hook_report.json": _reports()["engine_hook"],
        "lsr_v2_trade_lifecycle_auto_monitor_report.json": _reports()["lifecycle"],
        "lsr_v2_telegram_trade_dashboard_report.json": _reports()["dashboard"],
        "lsr_v2_three_trade_postmortem_stability_lock_report.json": _reports()["postmortem"],
        "paper_state.json": {"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75},
        "paper_status.json": {"open_positions": 0, "pending_orders": 0},
    }
    for name, payload in mapping.items():
        (data / name).write_text(json.dumps(payload), encoding="utf-8")

    root = tmp_path
    for rel, markers in {
        "trading_bot/core/lsr_v2_fourth_trade_candidate_detection_audit.py": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT fourth_trade_candidate_detected_diagnostic candidate_routing_execution_allowed",
        "trading_bot/core/lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py": "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT candidate_detection_preflight_ready",
        "trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py": "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT candidate_lifecycle_hook_preflight_ready",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markers, encoding="utf-8")

    report = build_lsr_v2_fourth_trade_route_preflight_report_from_files(data_dir=data, project_root=root)
    assert report["status"] == "PASS"
    assert (data / "lsr_v2_fourth_trade_route_preflight_report.json").exists()
    assert (data / "lsr_v2_fourth_trade_route_preflight.jsonl").exists()
    assert report["paper_state_modified_by_route_preflight"] is False
    assert report["paper_status_modified_by_route_preflight"] is False


def test_route_preflight_warns_if_required_reports_missing():
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports={},
        paper_state={"positions": {}, "orders": {}},
        paper_status={"open_positions": 0, "pending_orders": 0},
        source_audit={"route_preflight_required_markers_present": True},
        env={"operator_env_absent": True, "route_preflight_operator_env_currently_active": False},
    )
    assert report["status"] == "WARN"
    assert "required_route_preflight_reports_not_ready" in report["blockers"]
