from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path

from trading_bot.core.paper_once_runner_footer import (
    load_lsr_v2_bridge_footer_summary,
    load_lsr_v2_engine_artifact_hook_footer_summary,
    print_runner_once_footer_from_events,
    read_latest_cycle_completed,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_runner_fallback_footer_includes_lsr_v2_bridge_report(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    started_at = datetime(2026, 5, 28, tzinfo=timezone.utc)
    _append_jsonl(
        events_path,
        {
            "ts": "2026-05-28T10:00:00+00:00",
            "event_type": "CYCLE_COMPLETED",
            "cycle_id": "pc_footer",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
            "errors": 0,
            "elapsed_seconds": 1.25,
        },
    )
    _write_json(
        tmp_path / "lsr_v2_paper_supervised_bridge_report.json",
        {
            "decision": "LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC",
            "bridge_events": 12,
            "candidate_ready_events": 12,
            "would_route_count": 0,
            "would_submit_count": 99,  # must be force-pinned in footer summary
            "orders_submitted_by_lsr_v2_bridge": 5,
            "positions_opened_by_lsr_v2_bridge": 7,
        },
    )

    stream = StringIO()
    printed = print_runner_once_footer_from_events(events_path, started_at=started_at, stream=stream, force=True)
    output = stream.getvalue()

    assert printed is True
    assert "prompt=29.4.4t-2" in output
    assert "footer_source=runner_event_fallback" in output
    assert "lsr_v2_bridge_decision=LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC" in output
    assert "lsr_v2_bridge_events=12" in output
    assert "lsr_v2_candidate_ready_events=12" in output
    assert "lsr_v2_would_route_count=0" in output
    assert "lsr_v2_would_submit_count=0" in output
    assert "orders_submitted_by_lsr_v2_bridge=0" in output
    assert "positions_opened_by_lsr_v2_bridge=0" in output


def test_runner_fallback_footer_prints_explicit_lsr_v2_missing_report_block(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(
        events_path,
        {
            "ts": "2026-05-28T10:00:00+00:00",
            "event_type": "CYCLE_COMPLETED",
            "cycle_id": "pc_missing_lsr",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
        },
    )

    stream = StringIO()
    printed = print_runner_once_footer_from_events(events_path, stream=stream, force=True)
    output = stream.getvalue()

    assert printed is True
    assert "lsr_v2_bridge_decision=KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_REPORT_MISSING" in output
    assert "lsr_v2_bridge_events=0" in output
    assert "lsr_v2_would_submit_count=0" in output
    assert "orders_submitted_by_lsr_v2_bridge=0" in output
    assert "positions_opened_by_lsr_v2_bridge=0" in output


def test_read_latest_cycle_completed_filters_by_started_at(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(events_path, {"ts": "2026-05-28T09:59:00+00:00", "event_type": "CYCLE_COMPLETED", "cycle_id": "old"})
    _append_jsonl(events_path, {"ts": "2026-05-28T10:01:00+00:00", "event_type": "CYCLE_COMPLETED", "cycle_id": "new"})

    latest = read_latest_cycle_completed(events_path, started_at=datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc))

    assert latest is not None
    assert latest["cycle_id"] == "new"


def test_lsr_v2_footer_summary_is_fail_closed_when_report_is_hostile(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "lsr_v2_paper_supervised_bridge_report.json",
        {
            "decision": "LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC",
            "would_submit_count": 4,
            "orders_submitted_by_lsr_v2_bridge": 2,
            "positions_opened_by_lsr_v2_bridge": 2,
            "broker_submit_called": True,
            "paper_order_submission_enabled": True,
            "execution_enabled": True,
            "routing_enabled": True,
            "promotion_ready": True,
        },
    )

    summary = load_lsr_v2_bridge_footer_summary(tmp_path)

    assert summary["would_submit_count"] == 0
    assert summary["orders_submitted_by_lsr_v2_bridge"] == 0
    assert summary["positions_opened_by_lsr_v2_bridge"] == 0
    assert summary["broker_submit_called"] is False
    assert summary["paper_order_submission_enabled"] is False
    assert summary["execution_enabled"] is False
    assert summary["routing_enabled"] is False
    assert summary["promotion_ready"] is False


def test_runner_fallback_counts_cycle_scoped_lsr_v2_events_from_paper_event_log(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(events_path, {"ts": "2026-05-28T09:59:00+00:00", "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT", "cycle_id": "pc_old", "candidate_ready": True})
    for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]:
        _append_jsonl(events_path, {
            "ts": "2026-05-28T10:00:00+00:00",
            "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT",
            "cycle_id": "pc_current",
            "symbol": symbol,
            "candidate_ready": symbol == "BTC/USDT",
        })
        _append_jsonl(events_path, {
            "ts": "2026-05-28T10:00:00+00:00",
            "event_type": "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT",
            "cycle_id": "pc_current",
            "symbol": symbol,
            "runtime_cycle_scoped": True,
            "would_route": symbol == "BTC/USDT",
            "operator_enable": True,
            "operator_confirmation_ok": True,
            "operator_authorized": True,
            "would_submit": True,  # hostile/malformed input must be pinned to zero in footer
            "orders_submitted_by_lsr_v2_runtime_bridge": 2,
            "positions_opened_by_lsr_v2_runtime_bridge": 1,
        })
    _append_jsonl(events_path, {
        "ts": "2026-05-28T10:00:01+00:00",
        "event_type": "CYCLE_COMPLETED",
        "cycle_id": "pc_current",
        "scanned": 4,
        "signals": 0,
        "orders": 0,
        "open_positions": 0,
    })

    stream = StringIO()
    printed = print_runner_once_footer_from_events(events_path, stream=stream, force=True)
    output = stream.getvalue()

    assert printed is True
    assert "prompt=29.4.4t-2" in output
    assert "lsr_v2_runtime_bridge_decision=LSR_V2_RUNTIME_CYCLE_BRIDGE_READY_DIAGNOSTIC" in output
    assert "lsr_v2_runtime_cycle_id=pc_current" in output
    assert "lsr_v2_runtime_bridge_events=4" in output
    assert "lsr_v2_runtime_candidate_events=4" in output
    assert "lsr_v2_runtime_candidate_ready_events=1" in output
    assert "lsr_v2_runtime_would_route_count=1" in output
    assert "lsr_v2_runtime_would_submit_count=0" in output
    assert "lsr_v2_operator_enable=true" in output
    assert "lsr_v2_operator_confirmation_ok=true" in output
    assert "orders_submitted_by_lsr_v2_runtime_bridge=0" in output
    assert "positions_opened_by_lsr_v2_runtime_bridge=0" in output



def test_runner_fallback_footer_includes_lsr_v2_engine_artifact_hook_report(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(
        events_path,
        {
            "ts": "2026-05-30T10:00:00+00:00",
            "event_type": "CYCLE_COMPLETED",
            "cycle_id": "pc_engine_footer",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
        },
    )
    _write_json(
        tmp_path / "lsr_v2_engine_read_only_artifact_hook_report.json",
        {
            "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
            "engine_artifact_hook_ready": True,
            "paper_engine_hook_read_only": True,
            "telegram_dashboard_ready": True,
            "telegram_payload_ready": True,
            "telegram_update_ready": True,
            "telegram_send_allowed": True,  # hostile/malformed report must be pinned false in footer
            "telegram_network_called": True,
            "visual_sl_tp_progress_bar_ready": True,
            "visual_sl_tp_progress_bar": "SL ================● TP",
            "lifecycle_state": "FLAT_LOCKED",
            "fourth_trade_locked": True,
            "stability_lock_active": True,
            "orders_submitted_by_engine_artifact_hook": 9,
            "positions_opened_by_engine_artifact_hook": 8,
            "positions_closed_by_engine_artifact_hook": 7,
            "broker_submit_called_by_engine_artifact_hook": True,
            "broker_close_called_by_engine_artifact_hook": True,
            "paper_state_modified_by_engine_artifact_hook": True,
            "paper_status_modified_by_engine_artifact_hook": True,
            "live_enabled": True,
            "testnet_enabled": True,
            "exchange_broker_enabled": True,
        },
    )

    stream = StringIO()
    printed = print_runner_once_footer_from_events(events_path, stream=stream, force=True)
    output = stream.getvalue()

    assert printed is True
    assert "prompt=29.4.4t-2" in output
    assert "lsr_v2_engine_hook_decision=LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY" in output
    assert "lsr_v2_lifecycle_state=FLAT_LOCKED" in output
    assert "lsr_v2_dashboard_ready=true" in output
    assert "lsr_v2_telegram_payload_ready=true" in output
    assert "lsr_v2_telegram_update_ready=true" in output
    assert "lsr_v2_telegram_send_allowed=false" in output
    assert "lsr_v2_visual_sl_tp_progress_bar_ready=true" in output
    assert "lsr_v2_visual_sl_tp_progress_bar=SL ================● TP" in output
    assert "lsr_v2_fourth_trade_locked=true" in output
    assert "lsr_v2_stability_lock_active=true" in output
    assert "orders_submitted_by_lsr_v2_engine_artifact_hook=0" in output
    assert "positions_opened_by_lsr_v2_engine_artifact_hook=0" in output
    assert "positions_closed_by_lsr_v2_engine_artifact_hook=0" in output


def test_lsr_v2_engine_artifact_hook_footer_summary_is_fail_closed_when_report_is_hostile(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "lsr_v2_engine_read_only_artifact_hook_report.json",
        {
            "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
            "telegram_send_allowed": True,
            "telegram_network_called": True,
            "orders_submitted_by_engine_artifact_hook": 3,
            "positions_opened_by_engine_artifact_hook": 2,
            "positions_closed_by_engine_artifact_hook": 1,
            "live_enabled": True,
            "testnet_enabled": True,
            "exchange_broker_enabled": True,
        },
    )

    summary = load_lsr_v2_engine_artifact_hook_footer_summary(tmp_path)

    assert summary["telegram_send_allowed"] is False
    assert summary["telegram_network_called"] is False
    assert summary["orders_submitted_by_engine_artifact_hook"] == 0
    assert summary["positions_opened_by_engine_artifact_hook"] == 0
    assert summary["positions_closed_by_engine_artifact_hook"] == 0
    assert summary["live_enabled"] is False
    assert summary["testnet_enabled"] is False
    assert summary["exchange_broker_enabled"] is False
