import json
from pathlib import Path

from core.lsr_v2_generic_paper_cycle_refactor_preflight import Settings, run_preflight


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_ready_reports(data: Path) -> None:
    _write(data / "lsr_v2_fourth_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY",
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "orders_submitted_by_submit_execution": 0,
        "positions_opened_by_submit_execution": 0,
        "broker_submit_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_payload_ready": True,
        "submit_execution_diagnostic": "NO_ORDER_SUBMIT_EXECUTION_DIAGNOSTIC",
    })
    _write(data / "lsr_v2_fourth_trade_submit_preflight_report.json", {
        "status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"
    })
    _write(data / "lsr_v2_fourth_trade_handoff_dry_run_report.json", {
        "status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"
    })
    _write(data / "lsr_v2_fourth_trade_route_preflight_report.json", {
        "status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"
    })
    _write(data / "lsr_v2_fourth_trade_candidate_detection_audit_report.json", {
        "status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY"
    })
    _write(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {
        "status": "PASS", "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY", "lifecycle_state": "FLAT_LOCKED"
    })
    _write(data / "lsr_v2_telegram_trade_dashboard_report.json", {
        "status": "PASS", "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", "dashboard_ready": True, "telegram_payload_ready": True
    })
    _write(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {
        "status": "PASS", "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "fourth_trade_locked": True, "stability_lock_active": True
    })
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_generic_refactor_preflight(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_FOURTH_TRADE_REARM_ENABLE", raising=False)
    data = tmp_path / "data"
    _seed_ready_reports(data)

    result = run_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"
    assert result["generic_cycle_refactor_preflight_ready"] is True
    assert result["ordinal_trade_patch_expansion_allowed"] is False
    assert result["fifth_trade_patch_allowed"] is False
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False
    assert result["paper_only_execution_allowed"] is False
    assert result["orders_submitted_by_generic_cycle_refactor_preflight"] == 0
    assert result["paper_state_modified_by_generic_cycle_refactor_preflight"] is False


def test_missing_upstream_report_warns(tmp_path):
    data = tmp_path / "data"
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["generic_cycle_refactor_preflight_ready"] is False
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_submit_execution_allowed"] is False


def test_active_lsr_v2_env_keeps_fail_closed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    _seed_ready_reports(data)
    monkeypatch.setenv("LSR_V2_SOME_OPERATOR_FLAG", "1")

    result = run_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["operator_env_absent"] is False
    assert result["active_lsr_v2_operator_env_count"] == 1
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False
    assert result["future_integrated_operation_allowed"] is False
