from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

from trading_bot.core.lsr_v2_launcher_read_only_dashboard_banner import (
    ENV_ACTIVE_DECISION,
    PASS_DECISION,
    REPORTS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files,
    emit_lsr_v2_launcher_read_only_dashboard_banner,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, open_position: bool = False, missing_dashboard: bool = False, live: bool = False) -> Path:
    data = tmp_path / "data"
    common_safe = {
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
    _write_json(
        data / "lsr_v2_launcher_read_only_visibility_preflight_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT_READY",
            "launcher_visibility_preflight_ready": True,
            "lifecycle_state": "FLAT_LOCKED",
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_engine_read_only_artifact_hook_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
            "engine_artifact_hook_ready": True,
            "lifecycle_state": "OPEN" if open_position else "FLAT_LOCKED",
            "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
            "telegram_payload_ready": True,
            "telegram_update_ready": True,
            "telegram_send_allowed": True,  # hostile input must be pinned false in banner
            "telegram_network_called": True,
            "visual_sl_tp_progress_bar_ready": True,
            "visual_sl_tp_progress_bar": "SL ================● TP",
            "submit_execution_events_total": 3,
            "close_execution_events_total": 3,
            "aggregate_realized_pnl": 23.7543376227,
            "balance_after": 1023.7543376227,
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_trade_lifecycle_auto_monitor_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
            "lifecycle_state": "OPEN" if open_position else "FLAT_LOCKED",
            "telegram_update_ready": True,
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_telegram_trade_dashboard_report.json",
        {
            "status": "WARN" if missing_dashboard else "PASS",
            "decision": "KEEP_DIAGNOSTIC" if missing_dashboard else "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
            "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
            "telegram_payload_ready": not missing_dashboard,
            "telegram_update_ready": not missing_dashboard,
            "telegram_send_allowed": True,
            "telegram_network_called": True,
            "visual_sl_tp_progress_bar_ready": True,
            "visual_sl_tp_progress_bar": "SL ================● TP",
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_three_trade_postmortem_stability_lock_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
            "submit_execution_events_total": 3,
            "close_execution_events_total": 3,
            "aggregate_realized_pnl": 23.7543376227,
            **common_safe,
        },
    )
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
    return data


def test_launcher_banner_passes_for_flat_locked_dashboard(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["launcher_banner_ready"] is True
    assert report["launcher_banner_print_allowed"] is True
    assert report["lifecycle_state"] == "FLAT_LOCKED"
    assert report["telegram_send_allowed"] is False
    assert report["telegram_network_called"] is False
    assert report["scheduler_started"] is False
    assert report["visual_sl_tp_progress_bar_ready"] is True
    assert "SL ================● TP" in report["launcher_banner_text"]
    assert report["orders_submitted_by_launcher_banner"] == 0
    assert report["positions_opened_by_launcher_banner"] == 0
    assert report["positions_closed_by_launcher_banner"] == 0
    assert report["paper_state_modified_by_launcher_banner"] is False
    assert report["paper_status_modified_by_launcher_banner"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_launcher_banner_warns_when_dashboard_not_ready(tmp_path: Path) -> None:
    data = _seed(tmp_path, missing_dashboard=True)
    report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_MISSING_DECISION
    assert "telegram_dashboard_not_ready" in report["blockers"]
    assert report["telegram_send_allowed"] is False


def test_launcher_banner_warns_when_not_flat_locked(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_launcher_banner_warns_when_operator_env_active(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_ARM", "1")
    report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_emit_launcher_banner_prints_read_only_text(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    printed: list[str] = []
    report = emit_lsr_v2_launcher_read_only_dashboard_banner(data_dir=data, print_func=printed.append)
    assert report["status"] == "PASS"
    assert printed
    assert "[LSR-V2 LAUNCHER DASHBOARD] READ-ONLY" in printed[0]
    assert "telegram_send=NO" in printed[0]


def test_avvia_bot_live_refuses_live_and_emits_banner(monkeypatch) -> None:
    fake_runner = types.ModuleType("run_paper_trading")
    fake_runner.main = lambda: None
    monkeypatch.setitem(sys.modules, "run_paper_trading", fake_runner)

    path = Path(__file__).resolve().parents[1] / "avvia_bot_live.py"
    spec = importlib.util.spec_from_file_location("avvia_bot_live_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[str] = []
    monkeypatch.setattr(module, "paper_main", lambda: calls.append("paper_main"))
    monkeypatch.setattr(module, "_emit_lsr_v2_read_only_banner", lambda: calls.append("banner"))
    monkeypatch.setattr(module.sys, "argv", ["avvia_bot_live.py", "--mode", "paper"])
    module.main()
    assert calls == ["banner", "paper_main"]

    monkeypatch.setattr(module.sys, "argv", ["avvia_bot_live.py", "--live"])
    try:
        module.main()
    except SystemExit as exc:
        assert "Live real-money execution is disabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("live mode was not refused")
