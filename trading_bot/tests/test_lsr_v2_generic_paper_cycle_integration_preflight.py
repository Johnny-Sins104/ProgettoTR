import json
from pathlib import Path

from core.lsr_v2_generic_paper_cycle_integration_preflight import Settings, run_generic_paper_cycle_integration_preflight


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_sources(root: Path) -> None:
    _write(root / "trading_bot/core/lsr_v2_paper_cycle_controller.py", {"marker": "GENERIC_LSR_V2_PAPER_CYCLE_CONTROLLER_DRAFT generic_cycle_controller"})
    _write(root / "trading_bot/core/lsr_v2_paper_order_lifecycle.py", {"marker": "GENERIC_LSR_V2_PAPER_ORDER_LIFECYCLE_DRAFT generic_order_lifecycle"})
    _write(root / "trading_bot/core/lsr_v2_supervised_rearm_policy.py", {"marker": "GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT generic_rearm"})


def _seed_ready_reports(data: Path) -> None:
    _write(data / "lsr_v2_supervised_rearm_policy_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY",
        "generic_supervised_rearm_policy_draft_ready": True,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
    })
    _write(data / "lsr_v2_paper_order_lifecycle_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY",
        "generic_order_lifecycle_draft_ready": True,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
    })
    _write(data / "lsr_v2_paper_cycle_controller_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY",
        "generic_cycle_controller_draft_ready": True,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
    })
    _write(data / "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY",
        "ordinal_trade_patch_expansion_allowed": False,
    })
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
        "positions_closed_by_submit_execution": 0,
        "broker_submit_called": False,
        "broker_close_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write(data / "lsr_v2_fourth_trade_submit_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"})
    _write(data / "lsr_v2_fourth_trade_handoff_dry_run_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"})
    _write(data / "lsr_v2_fourth_trade_route_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"})
    _write(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {"status": "PASS", "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"})
    _write(data / "lsr_v2_telegram_trade_dashboard_report.json", {"status": "PASS", "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", "telegram_payload_ready": True})
    _write(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {"status": "PASS", "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "fourth_trade_locked": True, "stability_lock_active": True})
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_generic_cycle_integration_preflight(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    data = tmp_path / "data"
    _seed_sources(tmp_path)
    _seed_ready_reports(data)

    result = run_generic_paper_cycle_integration_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY"
    assert result["generic_cycle_integration_preflight_ready"] is True
    assert result["generic_controller_ready"] is True
    assert result["generic_order_lifecycle_ready"] is True
    assert result["generic_rearm_policy_ready"] is True
    assert result["generic_engine_integration_map_ready"] is True
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False
    assert result["generic_submit_execution_allowed"] is False
    assert result["paper_only_execution_allowed"] is False
    assert result["orders_submitted_by_generic_cycle_integration_preflight"] == 0


def test_missing_rearm_policy_report_warns(tmp_path):
    _seed_sources(tmp_path)
    _write(tmp_path / "data/paper_state.json", {"orders": {}, "positions": {}})
    _write(tmp_path / "data/paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_generic_paper_cycle_integration_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["generic_cycle_integration_preflight_ready"] is False
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False


def test_missing_source_marker_warns_fail_closed(tmp_path):
    data = tmp_path / "data"
    _seed_ready_reports(data)
    _write(tmp_path / "trading_bot/core/lsr_v2_paper_cycle_controller.py", {"marker": "missing"})
    _write(tmp_path / "trading_bot/core/lsr_v2_paper_order_lifecycle.py", {"marker": "GENERIC_LSR_V2_PAPER_ORDER_LIFECYCLE_DRAFT generic_order_lifecycle"})
    _write(tmp_path / "trading_bot/core/lsr_v2_supervised_rearm_policy.py", {"marker": "GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT generic_rearm"})

    result = run_generic_paper_cycle_integration_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "generic_source_markers_missing" in result["blockers"]
    assert result["generic_required_source_markers_present"] is False
    assert result["generic_submit_execution_allowed"] is False


def test_integration_map_is_read_only_and_non_ordinal(tmp_path):
    data = tmp_path / "data"
    _seed_sources(tmp_path)
    _seed_ready_reports(data)

    result = run_generic_paper_cycle_integration_preflight(Settings(project_root=tmp_path))
    integration_map = result["generic_paper_cycle_integration_map"]

    assert integration_map["execution_enabled"] is False
    assert integration_map["mutation_enabled"] is False
    assert integration_map["ordinal_module_generation_allowed"] is False
    assert len(integration_map["stages"]) >= 10
    assert all(stage["execution_allowed"] is False for stage in integration_map["stages"])
    assert result["fifth_trade_patch_allowed"] is False
    assert result["sixth_trade_patch_allowed"] is False
    assert result["seventh_trade_patch_allowed"] is False
