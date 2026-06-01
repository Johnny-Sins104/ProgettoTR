import json
from pathlib import Path

from core.lsr_v2_generic_paper_cycle_engine_hook_preflight import Settings, run_generic_paper_cycle_engine_hook_preflight


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_sources(root: Path) -> None:
    _write(root / "trading_bot/core/paper_engine.py", "class PaperTradingEngine: pass\ndef write_lsr_v2_engine_read_only_artifact_hook_report(): pass\n")
    _write(root / "trading_bot/run_paper_trading.py", "--no-lsr-v2-engine-read-only-artifact-hook\n")
    _write(root / "trading_bot/core/lsr_v2_generic_paper_cycle_integration_preflight.py", "GENERIC_LSR_V2_PAPER_CYCLE_INTEGRATION_PREFLIGHT generic_paper_cycle_integration_map\n")
    _write(root / "trading_bot/core/lsr_v2_paper_cycle_controller.py", "GENERIC_LSR_V2_PAPER_CYCLE_CONTROLLER_DRAFT generic_controller_state_machine\n")
    _write(root / "trading_bot/core/lsr_v2_paper_order_lifecycle.py", "GENERIC_LSR_V2_PAPER_ORDER_LIFECYCLE_DRAFT generic_order_lifecycle_state_model\n")
    _write(root / "trading_bot/core/lsr_v2_supervised_rearm_policy.py", "GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT generic_rearm_policy_state_model\n")


def _seed_ready_reports(data: Path) -> None:
    _write(data / "lsr_v2_generic_paper_cycle_integration_preflight_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY",
        "generic_cycle_integration_preflight_ready": True,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_generic_cycle_integration_preflight": 0,
        "positions_opened_by_generic_cycle_integration_preflight": 0,
        "positions_closed_by_generic_cycle_integration_preflight": 0,
        "broker_submit_called_by_generic_cycle_integration_preflight": False,
        "broker_close_called_by_generic_cycle_integration_preflight": False,
    })
    _write(data / "lsr_v2_supervised_rearm_policy_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY",
        "ordinal_trade_patch_expansion_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
    })
    _write(data / "lsr_v2_paper_order_lifecycle_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY",
        "ordinal_trade_patch_expansion_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
    })
    _write(data / "lsr_v2_paper_cycle_controller_draft_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY",
        "ordinal_trade_patch_expansion_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
    })
    _write(data / "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY",
    })
    _write(data / "lsr_v2_engine_read_only_artifact_hook_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {"status": "PASS", "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"})
    _write(data / "lsr_v2_telegram_trade_dashboard_report.json", {"status": "PASS", "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", "telegram_payload_ready": True})
    _write(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {"status": "PASS", "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "fourth_trade_locked": True, "stability_lock_active": True})
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_generic_cycle_engine_hook_preflight(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    data = tmp_path / "data"
    _seed_sources(tmp_path)
    _seed_ready_reports(data)

    result = run_generic_paper_cycle_engine_hook_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY"
    assert result["generic_cycle_engine_hook_preflight_ready"] is True
    assert result["generic_engine_hook_map_ready"] is True
    assert result["generic_paper_cycle_integration_ready"] is True
    assert result["generic_controller_ready"] is True
    assert result["generic_order_lifecycle_ready"] is True
    assert result["generic_rearm_policy_ready"] is True
    assert result["generic_cycle_engine_hook_execution_allowed"] is False
    assert result["paper_engine_mutation_allowed"] is False
    assert result["generic_submit_execution_allowed"] is False
    assert result["orders_submitted_by_generic_cycle_engine_hook_preflight"] == 0


def test_missing_integration_report_warns_fail_closed(tmp_path):
    _seed_sources(tmp_path)
    _write(tmp_path / "data/paper_state.json", {"orders": {}, "positions": {}})
    _write(tmp_path / "data/paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_generic_paper_cycle_engine_hook_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_cycle_engine_hook_execution_allowed"] is False
    assert result["paper_only_execution_allowed"] is False


def test_missing_paper_engine_marker_warns_fail_closed(tmp_path):
    data = tmp_path / "data"
    _seed_ready_reports(data)
    _seed_sources(tmp_path)
    _write(tmp_path / "trading_bot/core/paper_engine.py", "class PaperTradingEngine: pass\n")

    result = run_generic_paper_cycle_engine_hook_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "generic_engine_hook_source_markers_missing" in result["blockers"]
    assert result["generic_engine_hook_required_markers_present"] is False
    assert result["generic_route_execution_allowed"] is False


def test_engine_hook_map_is_read_only_and_non_ordinal(tmp_path):
    data = tmp_path / "data"
    _seed_sources(tmp_path)
    _seed_ready_reports(data)

    result = run_generic_paper_cycle_engine_hook_preflight(Settings(project_root=tmp_path))
    hook_map = result["generic_paper_cycle_engine_hook_map"]

    assert hook_map["execution_enabled"] is False
    assert hook_map["mutation_enabled"] is False
    assert hook_map["broker_submit_enabled"] is False
    assert hook_map["ordinal_module_generation_allowed"] is False
    assert len(hook_map["stages"]) >= 10
    assert all(stage["execution_allowed"] is False for stage in hook_map["stages"])
    assert result["fifth_trade_patch_allowed"] is False
    assert result["sixth_trade_patch_allowed"] is False
    assert result["seventh_trade_patch_allowed"] is False
