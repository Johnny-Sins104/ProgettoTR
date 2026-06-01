from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_paper_only_candidate_detection_readiness_preflight import (
    KEEP_DIAGNOSTIC_DECISION,
    READY_DECISION,
    Settings,
    run_generic_paper_only_candidate_detection_readiness_preflight,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_source_markers(root: Path) -> None:
    files = {
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.py":
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK\nadapter_visibility_parity_locked\n",
        "trading_bot/core/paper_engine.py": "class PaperTradingEngine: pass\n",
        "trading_bot/run_paper_trading.py": "# no-lsr-v2-engine-read-only-artifact-hook\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _lock_payload(**overrides: object) -> dict:
    payload = {
        "status": "PASS",
        "decision": "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_READY",
        "adapter_visibility_parity_locked": True,
        "lifecycle_state": "FLAT_LOCKED",
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "paper_state_status_consistency": True,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_execution_allowed": False,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed": False,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
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
        "orders_submitted_by_engine_runner_adapter_visibility_parity_lock": 0,
        "positions_opened_by_engine_runner_adapter_visibility_parity_lock": 0,
        "positions_closed_by_engine_runner_adapter_visibility_parity_lock": 0,
        "paper_state_modified_by_engine_runner_adapter_visibility_parity_lock": False,
        "paper_status_modified_by_engine_runner_adapter_visibility_parity_lock": False,
    }
    payload.update(overrides)
    return payload


def _project(tmp_path: Path) -> Settings:
    _write_source_markers(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json",
        _lock_payload(),
    )
    return Settings(project_root=tmp_path)


def test_candidate_detection_readiness_passes_and_remains_fail_closed(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    report = run_generic_paper_only_candidate_detection_readiness_preflight(settings)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["generic_candidate_detection_readiness_ready"] is True
    assert report["generic_candidate_detection_map_ready"] is True
    assert report["candidate_detection_scan_executed"] is False
    assert report["generic_candidate_detection_allowed"] is False
    assert report["generic_route_execution_allowed"] is False
    assert report["generic_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_generic_candidate_detection_readiness_preflight"] == 0
    assert report["positions_opened_by_generic_candidate_detection_readiness_preflight"] == 0
    assert report["paper_state_modified_by_generic_candidate_detection_readiness_preflight"] is False
    assert (tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight_report.json").exists()
    assert (tmp_path / "data" / "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.jsonl").exists()


def test_candidate_detection_readiness_warns_when_lock_missing(tmp_path: Path) -> None:
    _write_source_markers(tmp_path)
    report = run_generic_paper_only_candidate_detection_readiness_preflight(Settings(project_root=tmp_path))

    assert report["status"] == "WARN"
    assert report["decision"] == KEEP_DIAGNOSTIC_DECISION
    assert "parity_lock_ready" in report["blockers"]
    assert report["generic_candidate_detection_allowed"] is False


def test_candidate_detection_readiness_warns_when_route_candidate_already_exists(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    _write_json(
        tmp_path / "data" / "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json",
        _lock_payload(route_candidate_available=True),
    )
    report = run_generic_paper_only_candidate_detection_readiness_preflight(settings)

    assert report["status"] == "WARN"
    assert "no_route_candidate" in report["blockers"]
    assert report["generic_candidate_scan_execution_allowed"] is False


def test_candidate_detection_readiness_warns_when_operator_env_present(tmp_path: Path, monkeypatch) -> None:
    settings = _project(tmp_path)
    monkeypatch.setenv("LSR_V2_GENERIC_REARM_ENABLE", "1")

    report = run_generic_paper_only_candidate_detection_readiness_preflight(settings)

    assert report["status"] == "WARN"
    assert report["operator_env_absent"] is False
    assert report["active_lsr_v2_operator_env_keys"] == ["LSR_V2_GENERIC_REARM_ENABLE"]
    assert report["paper_only_execution_allowed"] is False


def test_candidate_detection_readiness_warns_when_source_marker_missing(tmp_path: Path) -> None:
    settings = _project(tmp_path)
    (tmp_path / "trading_bot" / "run_paper_trading.py").write_text("# marker removed\n", encoding="utf-8")

    report = run_generic_paper_only_candidate_detection_readiness_preflight(settings)

    assert report["status"] == "WARN"
    assert "source_markers_present" in report["blockers"]
    assert report["generic_candidate_detection_required_markers_present"] is False
