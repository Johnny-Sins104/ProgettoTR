from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock import (
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_source_markers(root: Path) -> None:
    files = {
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit.py":
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT\nadapter_parity_mismatches\n",
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py":
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK\ngeneric_engine_runner_read_only_adapter_payload\n",
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "# no-lsr-v2-engine-read-only-artifact-hook\n",
        "trading_bot/avvia_bot_live.py": "emit_lsr_v2_launcher_read_only_dashboard_banner\nLive real-money execution is disabled\n",
        "avvia_bot_live.bat": "LSR-v2 read-only dashboard banner\nno Telegram send\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _audit_payload(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT_READY",
        "engine_adapter_visibility_parity_ok": True,
        "paper_runner_adapter_visibility_parity_ok": True,
        "launcher_adapter_visibility_parity_ok": True,
        "console_visibility_adapter_parity_ok": True,
        "adapter_safety_payload_parity_ok": True,
        "adapter_contract_parity_ok": True,
        "runtime_snapshot_marker_parity_ok": True,
        "lifecycle_state_parity_ok": True,
        "engine_runner_launcher_console_parity_ok": True,
        "adapter_parity_mismatches": [],
        "adapter_marker_values": {"engine": "READY_READ_ONLY", "paper_runner": "READY_READ_ONLY", "launcher": "READY_READ_ONLY"},
        "adapter_safety_payload": {
            "orders_submitted": 0,
            "positions_opened": 0,
            "positions_closed": 0,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        },
        "runtime_snapshot_visible_read_only": True,
        "lifecycle_state": "FLAT_LOCKED",
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "paper_state_status_consistency": True,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed": False,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed": False,
        "engine_read_only_adapter_execution_allowed": False,
        "paper_runner_adapter_execution_allowed": False,
        "launcher_adapter_execution_allowed": False,
        "console_visibility_adapter_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_engine_runner_adapter_visibility_parity_audit": 0,
        "positions_opened_by_engine_runner_adapter_visibility_parity_audit": 0,
        "positions_closed_by_engine_runner_adapter_visibility_parity_audit": 0,
        "paper_state_modified_by_engine_runner_adapter_visibility_parity_audit": False,
        "paper_status_modified_by_engine_runner_adapter_visibility_parity_audit": False,
    }
    payload.update(overrides)
    return payload


def _adapter_hook_payload(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY",
        "adapter_payload_bridge_ready": True,
    }
    payload.update(overrides)
    return payload


def _project(tmp_path: Path) -> Settings:
    _write_source_markers(tmp_path)
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_report.json", _audit_payload())
    _write_json(data / "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json", _adapter_hook_payload())
    return Settings(project_root=tmp_path)


def test_visibility_parity_lock_passes_and_remains_fail_closed(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(settings)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_ready"] is True
    assert report["adapter_visibility_parity_locked"] is True
    assert report["engine_runner_launcher_console_parity_locked"] is True
    assert report["generic_submit_execution_allowed"] is False
    assert report["generic_close_execution_allowed"] is False
    assert report["paper_engine_mutation_allowed"] is False
    assert report["orders_submitted_by_engine_runner_adapter_visibility_parity_lock"] == 0
    assert report["positions_opened_by_engine_runner_adapter_visibility_parity_lock"] == 0
    assert report["paper_state_modified_by_engine_runner_adapter_visibility_parity_lock"] is False
    assert (tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json").exists()
    assert (tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.jsonl").exists()


def test_visibility_parity_lock_warns_when_audit_missing(tmp_path: Path) -> None:
    _write_source_markers(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json",
        _adapter_hook_payload(),
    )
    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "parity_audit_ready" in report["blockers"]
    assert report["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_execution_allowed"] is False


def test_visibility_parity_lock_warns_on_mismatch(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_report.json",
        _audit_payload(adapter_parity_mismatches=["runner_footer_payload.lifecycle_state"], lifecycle_state_parity_ok=False),
    )

    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(settings)

    assert report["status"] == "WARN"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert report["adapter_visibility_parity_locked"] is False
    assert "all_adapter_parity_ok" in report["blockers"]
    assert "no_adapter_parity_mismatches" in report["blockers"]


def test_visibility_parity_lock_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    settings = _project(tmp_path)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(settings)

    assert report["status"] == "WARN"
    assert report["operator_env_absent"] is False
    assert report["active_lsr_v2_operator_env_keys"] == ["LSR_V2_GENERIC_REARM_ENABLE"]
    assert report["generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_execution_allowed"] is False


def test_visibility_parity_lock_warns_when_source_marker_missing(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    (tmp_path / "trading_bot" / "run_paper_trading.py").write_text("# marker removed\n", encoding="utf-8")

    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(settings)

    assert report["status"] == "WARN"
    assert "source_markers_present" in report["blockers"]
    assert report["generic_engine_runner_adapter_visibility_parity_lock_required_markers_present"] is False
