import json
from pathlib import Path

from core.lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight import (
    READY_DECISION,
    Settings,
    run_generic_runtime_snapshot_footer_banner_wiring_preflight,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_sources(root: Path) -> None:
    _write(
        root / "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.py",
        "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT generic_runtime_visibility_map\n",
    )
    _write(
        root / "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py",
        "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK generic_runtime_snapshot\n",
    )
    _write(
        root / "trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py",
        "GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT generic_paper_cycle_runner_launcher_hook_map\n",
    )
    _write(root / "trading_bot/core/paper_once_runner_footer.py", "footer\n")
    _write(root / "trading_bot/run_paper_trading.py", "--no-lsr-v2-engine-read-only-artifact-hook\n")
    _write(root / "trading_bot/avvia_bot_live.py", "emit_lsr_v2_launcher_read_only_dashboard_banner\nLive real-money execution is disabled\n")
    _write(root / "avvia_bot_live.bat", "LSR-v2 read-only dashboard banner\nno Telegram send\n")


def _seed_report(data: Path, filename: str, decision: str, extra=None) -> None:
    payload = {"status": "PASS", "decision": decision}
    if extra:
        payload.update(extra)
    _write(data / filename, payload)


def _seed_ready_reports(data: Path) -> None:
    common = {
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "lifecycle_state": "FLAT_LOCKED",
        "runner_visibility_ready": True,
        "launcher_visibility_ready": True,
        "visibility_parity_ok": True,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_started": False,
    }
    runtime_snapshot = {
        "generic_cycle_state": {
            "lifecycle_state": "FLAT_LOCKED",
            "fourth_trade_locked": True,
            "stability_lock_active": True,
            "route_candidate_available": False,
            "paper_order_intent_ready": False,
        },
        "generic_rearm_policy_state": {"ready": True},
        "generic_order_lifecycle_state": {"ready": True},
        "runner_launcher_visibility_state": {
            "runner_visibility_ready": True,
            "launcher_visibility_ready": True,
            "visibility_parity_ok": True,
        },
        "safety_state": {
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
        },
    }
    _seed_report(data, "lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY", {
        **common,
        "generic_runtime_snapshot_visibility_preflight_ready": True,
        "runtime_snapshot_footer_fields_ready": True,
        "runtime_snapshot_banner_fields_ready": True,
        "runtime_snapshot_safety_fields_ready": True,
        "generic_runtime_snapshot_artifact_ready": True,
    })
    _seed_report(data, "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY", {
        **common,
        "generic_runtime_snapshot_artifact_ready": True,
        "generic_runtime_snapshot": runtime_snapshot,
    })
    _seed_report(data, "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY", common)
    _seed_report(data, "lsr_v2_generic_paper_cycle_engine_hook_preflight_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY", common)
    _seed_report(data, "lsr_v2_generic_paper_cycle_integration_preflight_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY", common)
    _seed_report(data, "lsr_v2_supervised_rearm_policy_draft_report.json", "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY", common)
    _seed_report(data, "lsr_v2_paper_order_lifecycle_draft_report.json", "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY", common)
    _seed_report(data, "lsr_v2_paper_cycle_controller_draft_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY", common)
    _seed_report(data, "lsr_v2_launcher_runner_visibility_parity_audit_report.json", "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY", {"launcher_runner_visibility_parity_ok": True, "visibility_mismatch_detected": False})
    _seed_report(data, "lsr_v2_launcher_read_only_dashboard_banner_report.json", "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY", {"launcher_banner_ready": True})
    _seed_report(data, "lsr_v2_engine_read_only_artifact_hook_report.json", "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY", {"engine_artifact_hook_ready": True})
    _seed_report(data, "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY", {"lifecycle_state": "FLAT_LOCKED"})
    _seed_report(data, "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY", {"telegram_payload_ready": True})
    _seed_report(data, "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", {"fourth_trade_locked": True})
    _write(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})


def test_ready_footer_banner_wiring_preflight(tmp_path, monkeypatch):
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)
    _seed_sources(tmp_path)
    _seed_ready_reports(tmp_path / "data")

    result = run_generic_runtime_snapshot_footer_banner_wiring_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == READY_DECISION
    assert result["generic_runtime_snapshot_footer_banner_wiring_preflight_ready"] is True
    assert result["runner_footer_wiring_preflight_ready"] is True
    assert result["launcher_banner_wiring_preflight_ready"] is True
    assert result["runtime_snapshot_footer_banner_parity_ready"] is True
    assert result["generic_runtime_snapshot_footer_banner_wiring_execution_allowed"] is False
    assert result["orders_submitted_by_generic_footer_banner_wiring_preflight"] == 0


def test_missing_visibility_report_warns_fail_closed(tmp_path):
    _seed_sources(tmp_path)
    _write(tmp_path / "data/paper_state.json", {"orders": {}, "positions": {}})
    _write(tmp_path / "data/paper_status.json", {"open_positions": 0, "pending_orders": 0})

    result = run_generic_runtime_snapshot_footer_banner_wiring_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_runtime_snapshot_footer_banner_wiring_execution_allowed"] is False
    assert result["generic_submit_execution_allowed"] is False


def test_active_operator_env_warns_fail_closed(tmp_path, monkeypatch):
    _seed_sources(tmp_path)
    _seed_ready_reports(tmp_path / "data")
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    result = run_generic_runtime_snapshot_footer_banner_wiring_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "active_lsr_v2_operator_env_present" in result["blockers"]
    assert result["operator_env_absent"] is False
    assert result["generic_runtime_snapshot_footer_banner_wiring_execution_allowed"] is False


def test_footer_banner_wiring_map_is_read_only(tmp_path):
    _seed_sources(tmp_path)
    _seed_ready_reports(tmp_path / "data")

    result = run_generic_runtime_snapshot_footer_banner_wiring_preflight(Settings(project_root=tmp_path))
    wiring_map = result["generic_runtime_snapshot_footer_banner_wiring_map"]

    assert wiring_map["execution_enabled"] is False
    assert wiring_map["mutation_enabled"] is False
    assert wiring_map["runner_footer_wiring_enabled"] is False
    assert wiring_map["launcher_banner_wiring_enabled"] is False
    assert wiring_map["broker_submit_enabled"] is False
    assert wiring_map["ordinal_module_generation_allowed"] is False
    assert len(wiring_map["stages"]) >= 12
    assert all(stage["execution_allowed"] is False for stage in wiring_map["stages"])
    assert result["fifth_trade_patch_allowed"] is False
    assert result["sixth_trade_patch_allowed"] is False
    assert result["seventh_trade_patch_allowed"] is False
