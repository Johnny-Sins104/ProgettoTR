import json
from pathlib import Path

from core.lsr_v2_paper_order_lifecycle import Settings, run_order_lifecycle_draft


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_ready_reports(data: Path) -> None:
    _write(data / "lsr_v2_paper_cycle_controller_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY",
        "generic_cycle_controller_draft_ready": True,
        "generic_trade_state_machine_ready": True,
        "generic_trade_cycle_contract_ready": True,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
    })
    _write(data / "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY",
    })
    _write(data / "lsr_v2_fourth_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY",
        "lifecycle_state": "FLAT_LOCKED",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "paper_order_intent": {},
        "orders_submitted_by_submit_execution": 0,
        "positions_opened_by_submit_execution": 0,
        "positions_closed_by_submit_execution": 0,
        "broker_submit_called": False,
        "broker_close_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "submit_execution_diagnostic": "NO_ORDER_SUBMIT_EXECUTION_DIAGNOSTIC",
    })
    _write(data / "lsr_v2_fourth_trade_submit_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"})
    _write(data / "lsr_v2_fourth_trade_handoff_dry_run_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"})
    _write(data / "lsr_v2_fourth_trade_route_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"})
    _write(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {"status": "PASS", "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"})
    _write(data / "lsr_v2_telegram_trade_dashboard_report.json", {"status": "PASS", "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", "telegram_payload_ready": True})
    _write(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {"status": "PASS", "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "fourth_trade_locked": True, "stability_lock_active": True})
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_order_lifecycle_draft(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_ORDER_LIFECYCLE_ENABLE", raising=False)
    data = tmp_path / "data"
    _seed_ready_reports(data)

    result = run_order_lifecycle_draft(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
    assert result["generic_order_lifecycle_draft_ready"] is True
    assert result["generic_order_lifecycle_contract_ready"] is True
    assert result["generic_order_lifecycle_state_model_ready"] is True
    assert result["generic_paper_order_intent_model_ready"] is True
    assert result["generic_submit_execution_allowed"] is False
    assert result["generic_close_execution_allowed"] is False
    assert result["paper_state_modified_by_generic_order_lifecycle_draft"] is False
    assert result["orders_submitted_by_generic_order_lifecycle_draft"] == 0


def test_missing_controller_report_warns(tmp_path):
    data = tmp_path / "data"
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_order_lifecycle_draft(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["generic_order_lifecycle_draft_ready"] is False
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_order_lifecycle_execution_allowed"] is False


def test_active_lsr_v2_env_keeps_lifecycle_fail_closed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    _seed_ready_reports(data)
    monkeypatch.setenv("LSR_V2_GENERIC_ORDER_LIFECYCLE_ENABLE", "1")

    result = run_order_lifecycle_draft(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["operator_env_absent"] is False
    assert result["active_lsr_v2_operator_env_count"] == 1
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False
    assert result["future_integrated_operation_allowed"] is False


def test_order_lifecycle_model_is_read_only_and_generic(tmp_path):
    data = tmp_path / "data"
    _seed_ready_reports(data)

    result = run_order_lifecycle_draft(Settings(project_root=tmp_path))
    model = result["generic_order_lifecycle_state_model"]
    contract = result["generic_order_lifecycle_contract"]

    assert contract["trade_ordinal"] == "N"
    assert contract["paper_order_intent_required_for_submit"] is True
    assert contract["ordinal_module_generation_allowed"] is False
    assert model["broker_submit_enabled"] is False
    assert model["broker_close_enabled"] is False
    assert model["paper_state_mutation_enabled"] is False
    assert "paper_order_intent" in model["fields"]
    assert "paper_close_result" in model["fields"]
    assert result["fifth_trade_patch_allowed"] is False
    assert result["sixth_trade_patch_allowed"] is False
