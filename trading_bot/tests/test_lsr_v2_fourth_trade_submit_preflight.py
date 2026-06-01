from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_fourth_trade_submit_preflight import (
    PASS_DECISION,
    build_lsr_v2_fourth_trade_submit_preflight_report,
    build_lsr_v2_fourth_trade_submit_preflight_report_from_files,
)


def _base_report(decision: str, **extra):
    payload = {
        "status": "PASS",
        "decision": decision,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_trade_allowed": False,
        "fourth_submit_or_reentry_detected": False,
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
    }
    payload.update(extra)
    return payload


def _reports(*, intent: bool = False, live: bool = False):
    paper_order_intent = {
        "symbol": "BTC/USDT",
        "side": "BUY",
        "trade_ordinal": 4,
        "cycle_id": "pc_test",
        "paper_order_source": "lsr_v2_fourth_trade_handoff_dry_run",
    } if intent else {}
    return {
        "handoff_dry_run": _base_report(
            "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY",
            handoff_dry_run_ready=True,
            candidate_handoff_dry_run_ready=True,
            route_candidate_available=intent,
            would_route=intent,
            would_create_order=intent,
            would_create_order_count=1 if intent else 0,
            paper_order_intent=paper_order_intent,
            paper_order_intent_ready=intent,
            would_submit=False,
            broker_submit_called=False,
            broker_close_called=False,
            handoff_blocked_reason="" if intent else "no_route_candidate_available",
            live_enabled=live,
        ),
        "route_preflight": _base_report("LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY", route_preflight_ready=True, candidate_routing_preflight_ready=True, route_candidate_available=intent, would_route=intent, would_submit=False),
        "candidate_detection_audit": _base_report("LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY", candidate_detection_audit_ready=True),
        "unlock_activation_candidate_preflight": _base_report("LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY", unlock_activation_candidate_preflight_ready=True),
        "unlock_activation_preflight": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY", operator_unlock_activation_preflight_ready=True),
        "unlock_draft": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY", operator_unlock_draft_ready=True),
        "operator_gate": _base_report("LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY", operator_rearm_gate_preflight_ready=True),
        "rearm_readiness": _base_report("LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY", rearm_readiness_preflight_ready=True),
        "candidate_hook": _base_report("LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY", candidate_lifecycle_hook_preflight_ready=True),
        "handoff": _base_report("LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY", read_only_handoff_preflight_ready=True),
        "parity": _base_report("LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY", visibility_parity_audit_ready=True),
        "engine_hook": _base_report("LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY", engine_artifact_hook_ready=True),
        "lifecycle": _base_report("LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY", lifecycle_auto_monitor_ready=True, lifecycle_state="FLAT_LOCKED"),
        "dashboard": _base_report("LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", dashboard_ready=True, visual_sl_tp_progress_bar_ready=True, visual_sl_tp_progress_bar="SL =====●===== TP", telegram_payload_ready=True, telegram_update_ready=True),
        "postmortem": _base_report("LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", three_trade_postmortem_complete=True, aggregate_realized_pnl=23.75),
    }


def _flat_state():
    return {"positions": {}, "orders": {}, "balance": 1023.75, "realized_pnl": 23.75}


def _flat_status():
    return {"open_positions": 0, "pending_orders": 0, "balance": 1023.75, "realized_pnl": 23.75}


def _source_ok():
    return {
        "submit_preflight_source_files_present": True,
        "submit_preflight_required_markers_present": True,
        "missing_submit_preflight_source_files": [],
        "missing_submit_preflight_source_markers": {},
    }


def test_submit_preflight_passes_without_order_intent_and_does_not_submit():
    report = build_lsr_v2_fourth_trade_submit_preflight_report(
        reports=_reports(intent=False),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["submit_preflight_ready"] is True
    assert report["paper_order_intent_ready"] is False
    assert report["would_submit"] is False
    assert report["submit_blocked_reason"] == "no_route_candidate_available"
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_submit_preflight"] == 0


def test_submit_preflight_validates_order_intent_diagnostic_but_still_does_not_submit():
    report = build_lsr_v2_fourth_trade_submit_preflight_report(
        reports=_reports(intent=True),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "PASS"
    assert report["paper_order_intent_ready"] is True
    assert report["submit_preflight_valid_order_intent"] is True
    assert report["submit_preflight_would_validate_order"] is True
    assert report["would_submit"] is False
    assert report["would_submit_to_paper_broker"] is False
    assert report["broker_submit_called"] is False
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_order_intent"]["trade_ordinal"] == 4


def test_submit_preflight_fails_closed_if_live_enabled():
    report = build_lsr_v2_fourth_trade_submit_preflight_report(
        reports=_reports(live=True),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "FAIL"
    assert "live_enabled" in report["blockers"]
    assert report["broker_submit_called"] is False
    assert report["paper_state_modified_by_submit_preflight"] is False


def test_submit_preflight_warns_on_operator_env():
    report = build_lsr_v2_fourth_trade_submit_preflight_report(
        reports=_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={"LSR_V2_FOURTH_TRADE_SUBMIT_ENABLE": "1"},
    )
    assert report["status"] == "WARN"
    assert "operator_env_active_for_submit_preflight" in report["blockers"]
    assert report["submit_preflight_operator_env_currently_active"] is True
    assert report["candidate_submit_execution_allowed"] is False


def test_submit_preflight_warns_on_missing_marker():
    source = _source_ok(); source["submit_preflight_required_markers_present"] = False
    source["missing_submit_preflight_source_markers"] = {"x.py": ["marker"]}
    report = build_lsr_v2_fourth_trade_submit_preflight_report(
        reports=_reports(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=source,
        env_map={},
    )
    assert report["status"] == "WARN"
    assert "submit_preflight_required_markers_missing" in report["blockers"]


def test_submit_preflight_from_files_writes_report(tmp_path: Path):
    data = tmp_path / "data"; data.mkdir()
    reports = _reports(intent=False)
    name_map = {
        "handoff_dry_run": "lsr_v2_fourth_trade_handoff_dry_run_report.json",
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
        "trading_bot/core/lsr_v2_fourth_trade_handoff_dry_run.py": "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN paper_order_intent_ready would_create_order",
        "trading_bot/core/lsr_v2_fourth_trade_route_preflight.py": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT would_route",
        "trading_bot/core/lsr_v2_fourth_trade_candidate_detection_audit.py": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT fourth_trade_candidate_detected_diagnostic",
    }
    for rel, text in files.items():
        path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
    report = build_lsr_v2_fourth_trade_submit_preflight_report_from_files(data_dir=data, project_root=root)
    assert report["status"] == "PASS"
    assert (data / "lsr_v2_fourth_trade_submit_preflight_report.json").exists()
    assert (data / "lsr_v2_fourth_trade_submit_preflight.jsonl").exists()
