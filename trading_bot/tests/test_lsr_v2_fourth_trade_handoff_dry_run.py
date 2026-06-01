from __future__ import annotations

from pathlib import Path
import json

from core.lsr_v2_fourth_trade_handoff_dry_run import (
    PASS_DECISION,
    build_lsr_v2_fourth_trade_handoff_dry_run_report,
    build_lsr_v2_fourth_trade_handoff_dry_run_report_from_files,
)


def _base_report(decision: str, **extra):
    payload = {"status": "PASS", "decision": decision}
    payload.update(extra)
    return payload


def _reports(*, would_route: bool = False, live: bool = False):
    route_candidate = {
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "event_type": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTED",
        "trade_ordinal": 4,
        "source_jsonl": "paper_events.jsonl",
    } if would_route else {}
    return {
        "route_preflight": _base_report(
            "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY",
            route_preflight_ready=True,
            candidate_routing_preflight_ready=True,
            route_candidate_available=would_route,
            route_candidate=route_candidate,
            would_route=would_route,
            would_submit=False,
            route_blocked_reason="" if would_route else "no_fourth_specific_candidate",
            fourth_trade_locked=True,
            stability_lock_active=True,
            live_enabled=live,
        ),
        "candidate_detection_audit": _base_report("LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY", candidate_detection_audit_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "unlock_activation_candidate_preflight": _base_report("LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY", unlock_activation_candidate_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "unlock_activation_preflight": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY", operator_unlock_activation_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "unlock_draft": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY", operator_unlock_draft_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "operator_gate": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY", operator_rearm_gate_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "rearm_readiness": _base_report("LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY", rearm_readiness_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "candidate_hook": _base_report("LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY", candidate_lifecycle_hook_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "handoff": _base_report("LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY", read_only_handoff_preflight_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "parity": _base_report("LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY", visibility_parity_audit_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "engine_hook": _base_report("LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY", engine_artifact_hook_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "lifecycle": _base_report("LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY", lifecycle_auto_monitor_ready=True, lifecycle_state="FLAT_LOCKED", fourth_trade_locked=True, stability_lock_active=True),
        "dashboard": _base_report("LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", dashboard_ready=True, visual_sl_tp_progress_bar_ready=True, visual_sl_tp_progress_bar="SL =====●===== TP", telegram_payload_ready=True, telegram_update_ready=True, fourth_trade_locked=True, stability_lock_active=True),
        "postmortem": _base_report("LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", three_trade_postmortem_complete=True, aggregate_realized_pnl=23.75, fourth_trade_locked=True, stability_lock_active=True),
    }


def _flat_state():
    return {"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75}


def _flat_status():
    return {"open_positions": 0, "pending_orders": 0, "balance": 1023.75, "realized_pnl": 23.75}


def _source_ok():
    return {
        "handoff_dry_run_source_files_present": True,
        "handoff_dry_run_required_markers_present": True,
        "missing_handoff_dry_run_source_files": [],
        "missing_handoff_dry_run_source_markers": {},
    }


def test_handoff_dry_run_passes_without_route_candidate_and_does_not_create_order():
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report(
        reports=_reports(would_route=False),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["handoff_dry_run_ready"] is True
    assert report["route_candidate_available"] is False
    assert report["would_create_order"] is False
    assert report["would_create_order_count"] == 0
    assert report["handoff_blocked_reason"] == "no_route_candidate_available"
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_handoff_dry_run"] == 0
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False


def test_handoff_dry_run_can_build_order_intent_diagnostic_when_route_candidate_exists():
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report(
        reports=_reports(would_route=True),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "PASS"
    assert report["would_create_order"] is True
    assert report["would_create_order_count"] == 1
    assert report["paper_order_intent_ready"] is True
    assert report["paper_order_intent"]["symbol"] == "BTC/USDT"
    assert report["paper_order_intent"]["side"] == "BUY"
    assert report["paper_order_intent"]["trade_ordinal"] == 4
    assert report["broker_submit_called"] is False
    assert report["would_submit_to_paper_broker"] is False
    assert report["candidate_submit_execution_allowed"] is False


def test_handoff_dry_run_fails_closed_if_live_enabled():
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report(
        reports=_reports(live=True),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "FAIL"
    assert "live_enabled" in report["blockers"]
    assert report["broker_submit_called"] is False
    assert report["paper_state_modified_by_handoff_dry_run"] is False


def test_handoff_dry_run_warns_on_operator_env():
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report(
        reports=_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={"LSR_V2_FOURTH_TRADE_HANDOFF_ENABLE": "1"},
    )
    assert report["status"] == "WARN"
    assert "operator_env_active_for_handoff_dry_run" in report["blockers"]
    assert report["handoff_dry_run_operator_env_currently_active"] is True
    assert report["candidate_submit_execution_allowed"] is False


def test_handoff_dry_run_warns_on_missing_marker():
    source = _source_ok(); source["handoff_dry_run_required_markers_present"] = False
    source["missing_handoff_dry_run_source_markers"] = {"x.py": ["marker"]}
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report(
        reports=_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=source,
        env_map={},
    )
    assert report["status"] == "WARN"
    assert "handoff_dry_run_required_markers_missing" in report["blockers"]


def test_handoff_dry_run_from_files_writes_report(tmp_path: Path):
    data = tmp_path / "data"; data.mkdir()
    reports = _reports(would_route=False)
    name_map = {
        "route_preflight": "lsr_v2_fourth_trade_route_preflight_report.json",
        "candidate_detection_audit": "lsr_v2_fourth_trade_candidate_detection_audit_report.json",
        "unlock_activation_candidate_preflight": "lsr_v2_fourth_trade_unlock_activation_candidate_preflight_report.json",
        "unlock_activation_preflight": "lsr_v2_fourth_trade_operator_unlock_activation_preflight_report.json",
        "unlock_draft": "lsr_v2_fourth_trade_operator_unlock_draft_report.json",
        "operator_gate": "lsr_v2_fourth_trade_operator_rearm_gate_preflight_report.json",
        "rearm_readiness": "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json",
        "candidate_hook": "lsr_v2_candidate_lifecycle_hook_preflight_report.json",
        "handoff": "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json",
        "parity": "lsr_v2_launcher_runner_visibility_parity_audit_report.json",
        "engine_hook": "lsr_v2_engine_read_only_artifact_hook_report.json",
        "lifecycle": "lsr_v2_trade_lifecycle_auto_monitor_report.json",
        "dashboard": "lsr_v2_telegram_trade_dashboard_report.json",
        "postmortem": "lsr_v2_three_trade_postmortem_stability_lock_report.json",
    }
    for key, filename in name_map.items():
        (data / filename).write_text(json.dumps(reports[key]), encoding="utf-8")
    (data / "paper_state.json").write_text(json.dumps(_flat_state()), encoding="utf-8")
    (data / "paper_status.json").write_text(json.dumps(_flat_status()), encoding="utf-8")
    root = tmp_path
    files = {
        "trading_bot/core/lsr_v2_fourth_trade_route_preflight.py": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT would_route route_candidate_available",
        "trading_bot/core/lsr_v2_fourth_trade_candidate_detection_audit.py": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT fourth_trade_candidate_detected_diagnostic",
        "trading_bot/core/lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py": "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT candidate_detection_preflight_ready",
    }
    for rel, text in files.items():
        path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
    report = build_lsr_v2_fourth_trade_handoff_dry_run_report_from_files(data_dir=data, project_root=root)
    assert report["status"] == "PASS"
    assert (data / "lsr_v2_fourth_trade_handoff_dry_run_report.json").exists()
    assert (data / "lsr_v2_fourth_trade_handoff_dry_run.jsonl").exists()
