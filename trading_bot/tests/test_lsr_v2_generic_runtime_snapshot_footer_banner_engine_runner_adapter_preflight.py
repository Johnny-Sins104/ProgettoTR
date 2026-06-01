from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight import (
    READY_DECISION,
    Settings,
    run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_project(root: Path) -> None:
    data = root / "data"
    upstream = {
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
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
            "scheduler_started": False,
            "generic_runtime_snapshot_artifact_ready": True,
            "generic_runtime_snapshot_footer_banner_read_only_wiring_hook_ready": True,
            "runtime_snapshot_visible_read_only": True,
        }
        if filename == "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json":
            payload["generic_runtime_snapshot_footer_banner_read_only_wiring_payload"] = {
                "runtime_snapshot_visible_read_only": True,
                "runtime_snapshot_sections": ["generic_cycle_state", "safety_state"],
                "runner_footer_payload": {
                    "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
                    "lifecycle_state": "FLAT_LOCKED",
                    "route_candidate_available": False,
                    "paper_order_intent_ready": False,
                    "open_positions_after": 0,
                    "pending_orders_after": 0,
                },
                "launcher_banner_payload": {
                    "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
                    "lifecycle_state": "FLAT_LOCKED",
                    "live_enabled": False,
                    "testnet_enabled": False,
                    "exchange_broker_enabled": False,
                },
                "console_visibility_payload": {
                    "runtime_snapshot_visible": True,
                    "execution_enabled": False,
                    "paper_only": True,
                },
                "safety_payload": {
                    "orders_submitted": 0,
                    "positions_opened": 0,
                    "positions_closed": 0,
                    "live_enabled": False,
                    "testnet_enabled": False,
                    "exchange_broker_enabled": False,
                },
            }
        if filename == "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json":
            payload["generic_runtime_snapshot"] = {
                "generic_cycle_state": {
                    "lifecycle_state": "FLAT_LOCKED",
                    "fourth_trade_locked": True,
                    "stability_lock_active": True,
                    "route_candidate_available": False,
                    "paper_order_intent_ready": False,
                }
            }
        _write_json(data / filename, payload)
    _write_json(data / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(data / "paper_status.json", {"open_positions": 0, "pending_orders": 0})

    _write(root / "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py", "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK generic_runtime_snapshot_footer_banner_read_only_wiring_payload")
    _write(root / "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight.py", "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT generic_runtime_snapshot_footer_banner_wiring_map")
    _write(root / "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py", "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK generic_runtime_snapshot")
    _write(root / "trading_bot/core/lsr_v2_generic_paper_cycle_engine_hook_preflight.py", "GENERIC_LSR_V2_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT generic_paper_cycle_engine_hook_map")
    _write(root / "trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py", "GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT generic_paper_cycle_runner_launcher_hook_map")
    _write(root / "trading_bot/core/paper_engine.py", "class PaperTradingEngine: pass")
    _write(root / "trading_bot/run_paper_trading.py", "no-lsr-v2-engine-read-only-artifact-hook")
    _write(root / "trading_bot/avvia_bot_live.py", "emit_lsr_v2_launcher_read_only_dashboard_banner Live real-money execution is disabled")
    _write(root / "avvia_bot_live.bat", "LSR-v2 read-only dashboard banner no Telegram send")


def test_adapter_preflight_passes_and_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.delenv("LSR_V2_GENERIC_REARM_ENABLE", raising=False)

    result = run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "PASS"
    assert result["decision"] == READY_DECISION
    assert result["generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_ready"] is True
    assert result["engine_read_only_adapter_preflight_ready"] is True
    assert result["paper_runner_adapter_preflight_ready"] is True
    assert result["launcher_adapter_preflight_ready"] is True
    assert result["console_visibility_adapter_preflight_ready"] is True
    assert result["generic_runtime_snapshot_footer_banner_engine_runner_adapter_execution_allowed"] is False
    assert result["engine_read_only_adapter_execution_allowed"] is False
    assert result["generic_submit_execution_allowed"] is False
    assert result["generic_close_execution_allowed"] is False
    assert result["paper_engine_mutation_allowed"] is False
    assert result["runner_mutation_allowed"] is False
    assert result["launcher_mutation_allowed"] is False
    assert result["orders_submitted_by_engine_runner_adapter_preflight"] == 0
    assert result["positions_opened_by_engine_runner_adapter_preflight"] == 0
    assert result["paper_state_modified_by_engine_runner_adapter_preflight"] is False
    assert (tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_report.json").exists()
    assert (tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.jsonl").exists()


def test_missing_upstream_report_warns(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    (tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json").unlink()

    result = run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "missing_upstream_reports" in result["blockers"]
    assert result["generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_ready"] is False
    assert result["generic_runtime_snapshot_footer_banner_engine_runner_adapter_execution_allowed"] is False


def test_operator_env_blocks_readiness_but_not_safety(tmp_path: Path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    result = run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "active_lsr_v2_operator_env_present" in result["blockers"]
    assert result["operator_env_absent"] is False
    assert result["active_lsr_v2_operator_env_keys"] == ["LSR_V2_GENERIC_REARM_ENABLE"]
    assert result["generic_submit_execution_allowed"] is False
    assert result["paper_only_execution_allowed"] is False


def test_route_candidate_blocks_adapter_preflight(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    report = tmp_path / "data/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json"
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["route_candidate_available"] = True
    _write_json(report, payload)

    result = run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight(Settings(project_root=tmp_path))

    assert result["status"] == "WARN"
    assert "route_candidate_present_unexpected_for_adapter_preflight" in result["blockers"]
    assert result["route_candidate_available"] is True
    assert result["generic_runtime_snapshot_footer_banner_engine_runner_adapter_execution_allowed"] is False
