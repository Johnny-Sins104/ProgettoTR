from __future__ import annotations

from core.lsr_v2_fourth_trade_candidate_detection_audit import (
    PASS_DECISION,
    FAILED_DECISION,
    build_lsr_v2_fourth_trade_candidate_detection_audit_report,
    _candidate_evidence_from_row,
)

def _pass(decision: str, **extra):
    out = {"status": "PASS", "decision": decision}
    out.update(extra)
    return out

def _base_reports():
    return {
        "unlock_activation_candidate_preflight": _pass("LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY", unlock_activation_candidate_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "unlock_activation_preflight": _pass("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY", operator_unlock_activation_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "unlock_draft": _pass("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY", operator_unlock_draft_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "operator_gate": _pass("LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY", operator_rearm_gate_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "rearm_readiness": _pass("LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY", rearm_readiness_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "candidate_hook": _pass("LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY", candidate_lifecycle_hook_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "handoff": _pass("LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY", read_only_handoff_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "parity": _pass("LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY", launcher_runner_visibility_parity_ok=True, fourth_trade_locked=True, stability_lock_active=True),
        "engine_hook": _pass("LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY", engine_artifact_hook_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "lifecycle": _pass("LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY", lifecycle_auto_monitor_ready=True, lifecycle_state="FLAT_LOCKED", fourth_trade_locked=True, stability_lock_active=True),
        "dashboard": _pass("LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", dashboard_ready=True, visual_sl_tp_progress_bar_ready=True, visual_sl_tp_progress_bar="SL =====●===== TP", telegram_payload_ready=True, telegram_update_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "postmortem": _pass("LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", three_trade_postmortem_complete=True, aggregate_realized_pnl=23.75, fourth_trade_locked=True, stability_lock_active=True),
    }

def _flat_state():
    return {"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75}

def _flat_status():
    return {"open_positions": 0, "pending_orders": 0, "balance": 1023.75, "realized_pnl": 23.75}

def _source_ok():
    return {
        "candidate_detection_source_files_present": True,
        "candidate_detection_required_markers_present": True,
        "missing_candidate_detection_source_files": [],
        "missing_candidate_detection_source_markers": {},
    }

def test_candidate_detection_audit_passes_without_candidate_and_stays_fail_closed():
    report = build_lsr_v2_fourth_trade_candidate_detection_audit_report(
        reports=_base_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        candidate_scan={
            "candidate_detection_audit_sources": [],
            "candidate_detection_audit_scanned_sources": [],
            "candidate_detected_diagnostic": False,
            "candidate_detected_diagnostic_count": 0,
            "fourth_trade_candidate_detected_diagnostic": False,
            "fourth_trade_candidate_detected_diagnostic_count": 0,
            "candidate_detection_latest_candidate": {},
            "candidate_detection_evidence_sample": [],
        },
        env_controls={"active_lsr_v2_operator_env_count": 0, "active_lsr_v2_operator_env_keys": [], "operator_env_absent": True, "candidate_detection_operator_env_currently_active": False},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["candidate_detection_audit_ready"] is True
    assert report["candidate_detected_diagnostic"] is False
    assert report["candidate_detection_allowed"] is False
    assert report["candidate_routing_execution_allowed"] is False
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_candidate_detection_audit"] == 0
    assert report["positions_opened_by_candidate_detection_audit"] == 0
    assert report["paper_state_modified_by_candidate_detection_audit"] is False

def test_candidate_detection_audit_can_report_diagnostic_candidate_but_stays_non_executing():
    scan = {
        "candidate_detection_audit_sources": ["paper_events.jsonl"],
        "candidate_detection_audit_scanned_sources": ["paper_events.jsonl"],
        "candidate_detected_diagnostic": True,
        "candidate_detected_diagnostic_count": 1,
        "fourth_trade_candidate_detected_diagnostic": True,
        "fourth_trade_candidate_detected_diagnostic_count": 1,
        "candidate_detection_latest_candidate": {"symbol": "BTC/USDT", "side": "BUY", "trade_ordinal": 4},
        "candidate_detection_evidence_sample": [{"symbol": "BTC/USDT", "side": "BUY", "trade_ordinal": 4}],
    }
    report = build_lsr_v2_fourth_trade_candidate_detection_audit_report(
        reports=_base_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        candidate_scan=scan,
        env_controls={"active_lsr_v2_operator_env_count": 0, "active_lsr_v2_operator_env_keys": [], "operator_env_absent": True, "candidate_detection_operator_env_currently_active": False},
    )
    assert report["status"] == "PASS"
    assert report["candidate_detected_diagnostic"] is True
    assert report["fourth_trade_candidate_detected_diagnostic"] is True
    assert report["candidate_detection_requires_route_preflight_patch"] is True
    assert report["candidate_routing_execution_allowed"] is False
    assert report["candidate_submit_execution_allowed"] is False

def test_operator_env_active_blocks_audit_with_warn():
    report = build_lsr_v2_fourth_trade_candidate_detection_audit_report(
        reports=_base_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        candidate_scan={"candidate_detected_diagnostic": False, "candidate_detected_diagnostic_count": 0, "fourth_trade_candidate_detected_diagnostic": False, "fourth_trade_candidate_detected_diagnostic_count": 0},
        env_controls={"active_lsr_v2_operator_env_count": 1, "active_lsr_v2_operator_env_keys": ["LSR_V2_FOURTH_TRADE_REARM_ENABLE"], "operator_env_absent": False, "candidate_detection_operator_env_currently_active": True},
    )
    assert report["status"] == "WARN"
    assert "operator_env_active_for_detection_audit" in report["blockers"]
    assert report["candidate_detection_allowed"] is False

def test_live_flag_hard_fails():
    reports = _base_reports()
    reports["dashboard"]["live_enabled"] = True
    report = build_lsr_v2_fourth_trade_candidate_detection_audit_report(
        reports=reports,
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        candidate_scan={"candidate_detected_diagnostic": False, "candidate_detected_diagnostic_count": 0, "fourth_trade_candidate_detected_diagnostic": False, "fourth_trade_candidate_detected_diagnostic_count": 0},
        env_controls={"active_lsr_v2_operator_env_count": 0, "active_lsr_v2_operator_env_keys": [], "operator_env_absent": True, "candidate_detection_operator_env_currently_active": False},
    )
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION

def test_candidate_evidence_parser_ignores_preflight_events():
    assert _candidate_evidence_from_row({
        "event_type": "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT",
        "candidate_detected": True,
        "symbol": "BTC/USDT",
    }) is None

def test_candidate_evidence_parser_accepts_fourth_candidate_event():
    evidence = _candidate_evidence_from_row({
        "event_type": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTED",
        "candidate_detected": True,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "trade_ordinal": 4,
    })
    assert evidence is not None
    assert evidence["symbol"] == "BTC/USDT"
    assert evidence["fourth_specific"] is True
