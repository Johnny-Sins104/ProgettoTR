import json
from pathlib import Path

from core.lsr_v2_supervised_rearm_policy import Settings, run_supervised_rearm_policy_draft


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_ready_reports(data: Path) -> None:
    _write(data / "lsr_v2_paper_order_lifecycle_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY",
        "generic_order_lifecycle_draft_ready": True,
        "generic_order_lifecycle_contract_ready": True,
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
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
    })
    _write(data / "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"})
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
    })
    _write(data / "lsr_v2_fourth_trade_submit_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"})
    _write(data / "lsr_v2_fourth_trade_handoff_dry_run_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"})
    _write(data / "lsr_v2_fourth_trade_route_preflight_report.json", {"status": "PASS", "decision": "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"})
    _write(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {"status": "PASS", "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"})
    _write(data / "lsr_v2_telegram_trade_dashboard_report.json", {"status": "PASS", "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", "telegram_payload_ready": True})
    _write(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {"status": "PASS", "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "fourth_trade_locked": True, "stability_lock_active": True})
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_supervised_rearm_policy_draft(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_CONFIRMATION", raising=False)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_MAX_POSITIONS", raising=False)
    data = tmp_path / "data"
    _seed_ready_reports(data)

    result = run_supervised_rearm_policy_draft(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY"
    assert result["generic_supervised_rearm_policy_draft_ready"] is True
    assert result["generic_rearm_policy_contract_ready"] is True
    assert result["generic_rearm_operator_gate_model_ready"] is True
    assert result["generic_cooldown_policy_model_ready"] is True
    assert result["generic_rearm_policy_execution_allowed"] is False
    assert result["generic_lsr_v2_paper_cycle_allowed"] is False
    assert result["paper_only_execution_allowed"] is False
    assert result["orders_submitted_by_generic_rearm_policy_draft"] == 0


def test_missing_order_lifecycle_report_warns(tmp_path):
    data = tmp_path / "data"
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_supervised_rearm_policy_draft(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["generic_supervised_rearm_policy_draft_ready"] is False
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_rearm_policy_execution_allowed"] is False


def test_active_lsr_v2_env_keeps_rearm_policy_fail_closed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    _seed_ready_reports(data)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    result = run_supervised_rearm_policy_draft(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert result["operator_env_absent"] is False
    assert result["active_lsr_v2_operator_env_count"] == 1
    assert result["generic_rearm_policy_execution_allowed"] is False
    assert result["future_integrated_operation_allowed"] is False


def test_rearm_policy_models_are_generic_and_read_only(tmp_path):
    data = tmp_path / "data"
    _seed_ready_reports(data)

    result = run_supervised_rearm_policy_draft(Settings(project_root=tmp_path))
    contract = result["generic_rearm_policy_contract"]
    gate = result["generic_rearm_operator_gate_model"]
    cooldown = result["generic_cooldown_policy_model"]
    model = result["generic_rearm_policy_state_model"]

    assert contract["trade_ordinal"] == "N"
    assert contract["max_open_positions"] == 1
    assert contract["ordinal_module_generation_allowed"] is False
    assert gate["confirmation_phrase"] == "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY"
    assert cooldown["cooldown_after_close_required"] is True
    assert model["execution_enabled"] is False
    assert model["broker_submit_enabled"] is False
    assert model["candidate_detection_enabled"] is False
    assert result["fifth_trade_patch_allowed"] is False
    assert result["sixth_trade_patch_allowed"] is False
    assert result["seventh_trade_patch_allowed"] is False
