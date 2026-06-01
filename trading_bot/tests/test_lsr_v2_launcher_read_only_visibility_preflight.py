from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_launcher_read_only_visibility_preflight import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    REPORTS_MISSING_DECISION,
    SOURCE_MARKERS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_launcher_sources(root: Path, *, missing_marker: bool = False) -> None:
    (root / "trading_bot" / "core").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot").mkdir(parents=True, exist_ok=True)
    (root / "trading_bot" / "avvia_bot_live.py").write_text(
        "from run_paper_trading import main as paper_main\n"
        "# Live real-money execution is disabled\n"
        "# --live --mode=live\n",
        encoding="utf-8",
    )
    (root / "avvia_bot_live.bat").write_text(
        "@echo off\n"
        "python avvia_bot_live.py --mode paper --timeframe 5m --cost-model conservative\n",
        encoding="utf-8",
    )
    runner_text = "from core.paper_engine import PaperTradingEngine\n# --once --lsr-v2 visibility\n"
    if missing_marker:
        runner_text = "# runner without expected markers\n"
    (root / "trading_bot" / "run_paper_trading.py").write_text(runner_text, encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    open_position: bool = False,
    missing_dashboard: bool = False,
    live: bool = False,
    missing_marker: bool = False,
) -> tuple[Path, Path]:
    data = tmp_path / "data"
    project = tmp_path / "project"
    _write_launcher_sources(project, missing_marker=missing_marker)

    postmortem = {
        "status": "PASS",
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    dashboard = {
        "status": "WARN" if missing_dashboard else "PASS",
        "decision": "KEEP_DIAGNOSTIC" if missing_dashboard else "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "telegram_payload_ready": not missing_dashboard,
        "telegram_update_ready": not missing_dashboard,
        "telegram_send_allowed": True,  # hostile input must remain pinned false in launcher preflight
        "telegram_network_called": True,
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    lifecycle = {
        "status": "PASS",
        "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
        "lifecycle_state": "OPEN" if open_position else "FLAT_LOCKED",
        "telegram_update_ready": True,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    integration = {
        "status": "PASS",
        "decision": "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY",
        "integration_preflight_ready": True,
    }
    engine_hook = {
        "status": "PASS",
        "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
        "engine_artifact_hook_ready": True,
        "lifecycle_state": "OPEN" if open_position else "FLAT_LOCKED",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "telegram_payload_ready": True,
        "telegram_update_ready": True,
        "telegram_send_allowed": True,  # hostile input must remain pinned false
        "telegram_network_called": True,
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
    }
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", postmortem)
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", dashboard)
    _write_json(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", lifecycle)
    _write_json(data / "lsr_v2_paper_engine_integration_preflight_report.json", integration)
    _write_json(data / "lsr_v2_engine_read_only_artifact_hook_report.json", engine_hook)
    _write_json(
        data / "paper_state.json",
        {
            "balance": 1023.7543376227,
            "realized_pnl": 23.7543376227,
            "positions": {
                "p1": {
                    "source": "lsr_v2_third_trade_submit_execution",
                    "status": "OPEN" if open_position else "CLOSED",
                    "open": open_position,
                }
            },
            "orders": {},
        },
    )
    _write_json(
        data / "paper_status.json",
        {
            "open_positions": 1 if open_position else 0,
            "pending_orders": 0,
            "live_enabled": live,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "operational_unlock_allowed": False,
        },
    )
    return data, project


def test_launcher_visibility_preflight_passes_for_flat_locked_state(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["launcher_visibility_preflight_ready"] is True
    assert report["launcher_visibility_allowed"] is False
    assert report["launcher_mutation_allowed"] is False
    assert report["launcher_execution_allowed"] is False
    assert report["launcher_console_wiring_allowed"] is False
    assert report["engine_hook_ready"] is True
    assert report["lifecycle_state"] == "FLAT_LOCKED"
    assert report["telegram_send_allowed"] is False
    assert report["telegram_network_called"] is False
    assert report["visual_sl_tp_progress_bar_ready"] is True
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_launcher_visibility_preflight"] == 0
    assert report["positions_opened_by_launcher_visibility_preflight"] == 0
    assert report["positions_closed_by_launcher_visibility_preflight"] == 0
    assert report["paper_state_modified_by_launcher_visibility_preflight"] is False
    assert report["paper_status_modified_by_launcher_visibility_preflight"] is False
    assert report["recommended_next_patch"].startswith("29.4.4t-4")


def test_launcher_visibility_preflight_warns_when_reports_missing(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_dashboard=True)
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_MISSING_DECISION
    assert "telegram_dashboard_not_ready" in report["blockers"]


def test_launcher_visibility_preflight_warns_when_state_not_flat(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_launcher_visibility_preflight_warns_when_operator_env_active(tmp_path: Path, monkeypatch) -> None:
    data, project = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_ARM", "1")
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_launcher_visibility_preflight_warns_when_source_markers_missing(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_marker=True)
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == SOURCE_MARKERS_MISSING_DECISION
    assert "launcher_source_markers_missing" in report["blockers"]


def test_launcher_visibility_preflight_fails_if_live_enabled(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, live=True)
    report = build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
