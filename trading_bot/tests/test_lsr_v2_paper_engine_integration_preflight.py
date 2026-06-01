from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_engine_integration_preflight import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    REPORTS_MISSING_DECISION,
    SOURCE_HOOKS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_paper_engine_integration_preflight_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_project_sources(root: Path, *, missing_marker: bool = False) -> None:
    paper_engine = root / "trading_bot" / "core" / "paper_engine.py"
    run_paper = root / "trading_bot" / "run_paper_trading.py"
    avvia = root / "trading_bot" / "avvia_bot_live.py"
    paper_engine.parent.mkdir(parents=True, exist_ok=True)
    run_paper.parent.mkdir(parents=True, exist_ok=True)
    avvia.parent.mkdir(parents=True, exist_ok=True)
    paper_engine.write_text(
        "class PaperTradingEngine: pass\n"
        "# lsr_v2 hook\n"
        + ("" if missing_marker else "def write_lsr_v2_runtime_bridge_report(): pass\n"),
        encoding="utf-8",
    )
    run_paper.write_text(
        "from core.paper_engine import PaperTradingEngine\n"
        "# --once runner\n"
        "# lsr-v2 operator visibility\n",
        encoding="utf-8",
    )
    avvia.write_text(
        "from run_paper_trading import main as paper_main\n"
        "# --live and --mode=live disabled\n",
        encoding="utf-8",
    )


def _seed(tmp_path: Path, *, open_position: bool = False, missing_dashboard: bool = False, live: bool = False, missing_marker: bool = False) -> tuple[Path, Path]:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _write_project_sources(project, missing_marker=missing_marker)
    postmortem = {
        "status": "PASS",
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "pnl_reconciliation_ok": True,
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    dashboard = {
        "status": "PASS" if not missing_dashboard else "WARN",
        "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY" if not missing_dashboard else "KEEP_DIAGNOSTIC",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
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
        "lifecycle_state": "FLAT_LOCKED" if not open_position else "OPEN",
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", postmortem)
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", dashboard)
    _write_json(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", lifecycle)
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


def test_integration_preflight_passes_for_flat_locked_state(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["integration_preflight_ready"] is True
    assert report["engine_integration_allowed"] is False
    assert report["engine_mutation_allowed"] is False
    assert report["runner_consolidation_allowed"] is False
    assert report["source_files_present"] is True
    assert report["required_source_markers_present"] is True
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_integration_preflight"] == 0
    assert report["positions_opened_by_integration_preflight"] == 0
    assert report["positions_closed_by_integration_preflight"] == 0
    assert report["paper_state_modified_by_integration_preflight"] is False
    assert report["paper_status_modified_by_integration_preflight"] is False
    assert report["recommended_next_patch"].startswith("29.4.4t-1")


def test_integration_preflight_warns_when_lifecycle_reports_missing(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_dashboard=True)
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_MISSING_DECISION
    assert "telegram_dashboard_not_ready" in report["blockers"]


def test_integration_preflight_warns_when_state_not_flat(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_integration_preflight_warns_when_operator_env_active(tmp_path: Path, monkeypatch) -> None:
    data, project = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_ARM", "1")
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_integration_preflight_warns_when_source_markers_missing(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_marker=True)
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == SOURCE_HOOKS_MISSING_DECISION
    assert "source_markers_missing" in report["blockers"]


def test_integration_preflight_fails_if_live_enabled(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, live=True)
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
