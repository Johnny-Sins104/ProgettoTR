from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit import (
    READY_DECISION,
    Settings,
    run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _adapter_payload() -> dict:
    return {
        "mode": "engine_runner_read_only_adapter_hook",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "engine_adapter_enabled": True,
        "paper_runner_adapter_enabled": True,
        "launcher_adapter_enabled": True,
        "console_visibility_adapter_enabled": True,
        "runtime_snapshot_visible_read_only": True,
        "runtime_snapshot_sections": ["generic_cycle_state", "safety_state"],
        "engine_read_only_adapter_payload": {
            "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
            "runtime_snapshot_visible_read_only": True,
            "paper_engine_mutation_allowed": False,
            "execution_enabled": False,
            "paper_only": True,
        },
        "paper_runner_adapter_payload": {
            "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
            "lifecycle_state": "FLAT_LOCKED",
            "fourth_trade_locked": True,
            "stability_lock_active": True,
            "route_candidate_available": False,
            "paper_order_intent_ready": False,
            "open_positions_after": 0,
            "pending_orders_after": 0,
            "generic_rearm_allowed": False,
            "generic_submit_execution_allowed": False,
            "generic_close_execution_allowed": False,
        },
        "launcher_adapter_payload": {
            "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
            "lifecycle_state": "FLAT_LOCKED",
            "launcher_visibility_ready": True,
            "runner_visibility_ready": True,
            "visibility_parity_ok": True,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_send_allowed": False,
        },
        "console_visibility_adapter_payload": {
            "runtime_snapshot_visible": True,
            "paper_only": True,
            "execution_enabled": False,
        },
        "adapter_safety_payload": {
            "orders_submitted": 0,
            "positions_opened": 0,
            "positions_closed": 0,
            "paper_state_mutation_allowed": False,
            "paper_status_mutation_allowed": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
        },
        "contracts": {
            "engine_read_only_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "paper_engine_mutation_allowed": False,
                "reads_runtime_snapshot_artifact": True,
            },
            "paper_runner_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "runner_mutation_allowed": False,
                "reads_footer_payload": True,
            },
            "launcher_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "launcher_mutation_allowed": False,
                "reads_banner_payload": True,
            },
            "console_visibility_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "mutation_allowed": False,
                "reads_console_payload": True,
            },
        },
    }


def _seed_project(root: Path) -> None:
    data = root / "data"
    upstream = {
        "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY",
        "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_report.json": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT_READY",
        "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK_READY",
        "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight_report.json": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT_READY",
        "lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY",
        "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY",
        "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY",
        "lsr_v2_generic_paper_cycle_engine_hook_preflight_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY",
        "lsr_v2_generic_paper_cycle_integration_preflight_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY",
        "lsr_v2_supervised_rearm_policy_draft_report.json": "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY",
        "lsr_v2_paper_order_lifecycle_draft_report.json": "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY",
        "lsr_v2_paper_cycle_controller_draft_report.json": "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY",
        "lsr_v2_launcher_runner_visibility_parity_audit_report.json": "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY",
        "lsr_v2_launcher_read_only_dashboard_banner_report.json": "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY",
        "lsr_v2_engine_read_only_artifact_hook_report.json": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
        "lsr_v2_trade_lifecycle_auto_monitor_report.json": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
        "lsr_v2_telegram_trade_dashboard_report.json": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
        "lsr_v2_three_trade_postmortem_stability_lock_report.json": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
    }
    for filename, decision in upstream.items():
        payload = {
            "status": "PASS",
            "decision": decision,
            "lifecycle_state": "FLAT_LOCKED",
            "fourth_trade_locked": True,
            "stability_lock_active": True,
            "route_candidate_available": False,
            "paper_order_intent_ready": False,
            "runner_visibility_ready": True,
            "launcher_visibility_ready": True,
            "visibility_parity_ok": True,
            "runtime_snapshot_visible_read_only": True,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
            "scheduler_started": False,
        }
        if filename == "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json":
            payload.update(
                {
                    "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_ready": True,
                    "adapter_payload_bridge_ready": True,
                    "engine_read_only_adapter_hook_ready": True,
                    "paper_runner_adapter_hook_ready": True,
                    "launcher_adapter_hook_ready": True,
                    "console_visibility_adapter_hook_ready": True,
                    "generic_engine_runner_read_only_adapter_payload": _adapter_payload(),
                }
            )
        _write_json(data / filename, payload)
    _write_json(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    _write(root / "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py", "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK generic_engine_runner_read_only_adapter_payload")
    _write(root / "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py", "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT generic_engine_runner_adapter_map")
    _write(root / "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py", "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK generic_runtime_snapshot_footer_banner_read_only_wiring_payload")
    _write(root / "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py", "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK generic_runtime_snapshot")
    _write(root / "trading_bot/core/paper_engine.py", "class PaperTradingEngine: pass")
    _write(root / "trading_bot/run_paper_trading.py", "no-lsr-v2-engine-read-only-artifact-hook")
    _write(root / "trading_bot/avvia_bot_live.py", "emit_lsr_v2_launcher_read_only_dashboard_banner Live real-money execution is disabled")
    _write(root / "avvia_bot_live.bat", "LSR-v2 read-only dashboard banner no Telegram send")


def test_visibility_parity_audit_passes_and_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)

    result = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == READY_DECISION
    assert result["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_ready"] is True
    assert result["engine_adapter_visibility_parity_ok"] is True
    assert result["paper_runner_adapter_visibility_parity_ok"] is True
    assert result["launcher_adapter_visibility_parity_ok"] is True
    assert result["console_visibility_adapter_parity_ok"] is True
    assert result["adapter_safety_payload_parity_ok"] is True
    assert result["engine_runner_launcher_console_parity_ok"] is True
    assert result["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed"] is False
    assert result["generic_submit_execution_allowed"] is False
    assert result["generic_close_execution_allowed"] is False
    assert result["paper_state_modified_by_engine_runner_adapter_visibility_parity_audit"] is False
    assert (tmp_path / "data/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_report.json").exists()
    assert (tmp_path / "data/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit.jsonl").exists()


def test_missing_u13_report_warns(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    (tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json").unlink()

    result = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_ready"] is False
    assert result["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed"] is False


def test_payload_mismatch_warns_without_enabling_execution(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    report = tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json"
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["generic_engine_runner_read_only_adapter_payload"]["paper_runner_adapter_payload"]["generic_lsr_v2_runtime_snapshot"] = "STALE"
    _write_json(report, payload)

    result = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "adapter_visibility_parity_mismatch" in result["blockers"]
    assert "runtime_snapshot_marker_mismatch" in result["adapter_parity_mismatches"]
    assert result["paper_runner_adapter_visibility_parity_ok"] is False
    assert result["generic_submit_execution_allowed"] is False
    assert result["paper_only_execution_allowed"] is False


def test_operator_env_blocks_readiness_but_not_safety(tmp_path: Path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    result = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "active_lsr_v2_operator_env_present" in result["blockers"]
    assert result["operator_env_absent"] is False
    assert result["active_lsr_v2_operator_env_keys"] == ["LSR_V2_GENERIC_REARM_ENABLE"]
    assert result["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed"] is False


def test_open_position_blocks_readiness(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _write_json(tmp_path / "data/paper_status.json", {"open_positions": 1, "pending_orders": 0})

    result = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "paper_state_status_not_flat" in result["blockers"]
    assert result["open_positions_after"] == 1
    assert result["paper_state_status_consistency"] is False
    assert result["orders_submitted_by_engine_runner_adapter_visibility_parity_audit"] == 0
