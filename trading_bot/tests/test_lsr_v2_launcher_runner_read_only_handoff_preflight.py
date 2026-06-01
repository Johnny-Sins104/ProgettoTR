from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_launcher_runner_read_only_handoff_preflight import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    REPORTS_NOT_READY_DECISION,
    SOURCE_MARKERS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_source_tree(root: Path, *, missing_marker: bool = False) -> None:
    files = {
        "trading_bot/avvia_bot_live.py": "from core.lsr_v2_launcher_read_only_dashboard_banner import emit\nprint('LSR-V2 LAUNCHER DASHBOARD')\n",
        "avvia_bot_live.bat": "echo LSR-v2 read-only launcher visibility\n",
        "trading_bot/run_paper_trading.py": "# run_paper_trading --no-lsr-v2-engine-read-only-artifact-hook\n",
        "trading_bot/core/paper_engine.py": "lsr_v2_engine_read_only_artifact_hook\ndef write_lsr_v2_engine_read_only_artifact_hook_report(): pass\n",
        "trading_bot/core/paper_once_runner_footer.py": "LSR_V2_ENGINE_ARTIFACT_HOOK_REPORT_NAME='x'\ndef load_lsr_v2_engine_artifact_hook_footer_summary(): pass\n",
    }
    if missing_marker:
        files["trading_bot/core/paper_engine.py"] = "# missing marker\n"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _seed(tmp_path: Path, *, live: bool = False, open_position: bool = False, missing_report: bool = False) -> tuple[Path, Path]:
    data = tmp_path / "data"
    project = tmp_path / "project"
    _write_source_tree(project)
    common_safe = {
        "status": "PASS",
        "lifecycle_state": "FLAT_LOCKED",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "telegram_payload_ready": True,
        "telegram_update_ready": True,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.75,
    }
    if not missing_report:
        _write_json(data / "lsr_v2_launcher_runner_visibility_parity_audit_report.json", {
            **common_safe,
            "decision": "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY",
            "launcher_runner_visibility_parity_ok": True,
            "visibility_mismatch_detected": False,
            "runner_footer_ready": True,
        })
    _write_json(data / "lsr_v2_launcher_read_only_dashboard_banner_report.json", {**common_safe, "decision": "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"})
    _write_json(data / "lsr_v2_engine_read_only_artifact_hook_report.json", {**common_safe, "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY", "integration_preflight_ready": True})
    _write_json(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {**common_safe, "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"})
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", {**common_safe, "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"})
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {**common_safe, "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY", "balance_after": 1023.75})
    positions = []
    if open_position:
        positions.append({"position_id": "p4", "status": "OPEN", "source": "lsr_v2_fourth_trade"})
    _write_json(data / "paper_state.json", {"balance": 1023.75, "realized_pnl": 23.75, "positions": positions, "orders": []})
    _write_json(data / "paper_status.json", {"open_positions": 1 if open_position else 0, "pending_orders": 0})
    return data, project



def test_runner_source_accepts_cli_hook_without_literal_function_marker(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    runner = project / "trading_bot/run_paper_trading.py"
    runner.write_text("# --no-lsr-v2-engine-read-only-artifact-hook only\n", encoding="utf-8")
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["handoff_required_markers_present"] is True


def test_handoff_preflight_passes_with_flat_locked_parity(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["read_only_handoff_preflight_ready"] is True
    assert report["handoff_consolidation_allowed"] is False
    assert report["future_integrated_operation_allowed"] is False
    assert report["fourth_trade_rearm_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_read_only_handoff_preflight"] == 0
    assert report["positions_opened_by_read_only_handoff_preflight"] == 0
    assert report["positions_closed_by_read_only_handoff_preflight"] == 0


def test_missing_parity_report_warns(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_report=True)
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_NOT_READY_DECISION
    assert "visibility_parity_not_ready" in report["blockers"]


def test_missing_source_marker_warns(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    _write_source_tree(project, missing_marker=True)
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == SOURCE_MARKERS_MISSING_DECISION
    assert "handoff_required_markers_missing" in report["blockers"]


def test_open_position_warns_state_not_locked(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_operator_env_warns(monkeypatch, tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_REARM_ENABLE", "1")
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["active_lsr_v2_operator_env_count"] == 1


def test_live_flag_fails_closed(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, live=True)
    report = build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
