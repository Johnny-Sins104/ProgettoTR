from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_supervised_bridge import (
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    LSRV2PaperSupervisedBridgeSettings,
    load_lsr_v2_paper_supervised_bridge_events,
    prepare_lsr_v2_runtime_bridge_event,
    write_lsr_v2_paper_supervised_bridge_report,
)
from trading_bot.core.paper_once_console_summary import build_paper_once_console_summary_lines


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for payload in payloads:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _promotion_pass(data_dir: Path) -> None:
    _write_json(
        data_dir / "lsr_v2_promotion_gate_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_PAPER_SUPERVISED_CANDIDATE",
            "paper_supervised_candidate": True,
            "paper_supervised_readiness_preflight_pass": True,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_called": False,
        },
    )


def _candidate(candidate_id: str = "cand_runtime") -> dict:
    return {
        "event_type": "LSR_V2_CANDIDATE_AUDIT",
        "candidate_id": candidate_id,
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "side": "BUY",
        "archetype": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "candidate_ready": True,
        "quality": {"grade": "A"},
        "levels": {"entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0},
    }


def test_bridge_events_can_be_loaded_for_runtime_append(tmp_path: Path) -> None:
    _promotion_pass(tmp_path)
    _append_jsonl(tmp_path / "lsr_v2_candidate_audit.jsonl", [_candidate("cand_1"), _candidate("cand_2")])

    report = write_lsr_v2_paper_supervised_bridge_report(tmp_path)
    events = load_lsr_v2_paper_supervised_bridge_events(tmp_path)

    assert report["bridge_events"] == 2
    assert len(events) == 2
    assert all(event["event_type"] == EVENT_TYPE for event in events)
    assert all(event["would_submit"] is False for event in events)


def test_runtime_bridge_event_is_force_pinned_fail_closed() -> None:
    runtime_event = prepare_lsr_v2_runtime_bridge_event(
        {
            "event_type": EVENT_TYPE,
            "would_route": True,
            "would_submit": True,  # hostile/stale value must be force-pinned false
            "routing_enabled": True,
            "execution_enabled": True,
            "paper_order_submission_enabled": True,
            "broker_submit_called": True,
            "orders_submitted_by_lsr_v2_bridge": 99,
            "positions_opened_by_lsr_v2_bridge": 99,
        }
    )

    assert runtime_event["runtime_integration_prompt_id"] == "29.4.4s-10f"
    assert runtime_event["runtime_bridge_integration"] is True
    assert runtime_event["would_submit"] is False
    assert runtime_event["routing_enabled"] is False
    assert runtime_event["execution_enabled"] is False
    assert runtime_event["paper_order_submission_enabled"] is False
    assert runtime_event["broker_submit_called"] is False
    assert runtime_event["orders_submitted_by_lsr_v2_runtime_bridge"] == 0
    assert runtime_event["positions_opened_by_lsr_v2_runtime_bridge"] == 0
    assert runtime_event["orders_submitted_by_lsr_v2_bridge"] == 0
    assert runtime_event["positions_opened_by_lsr_v2_bridge"] == 0


def test_authorized_operator_routes_only_diagnostic_never_submit(tmp_path: Path) -> None:
    _promotion_pass(tmp_path)
    _append_jsonl(tmp_path / "lsr_v2_candidate_audit.jsonl", [_candidate("cand_auth")])
    settings = LSRV2PaperSupervisedBridgeSettings(
        operator_enable=True,
        operator_confirmation=CONFIRMATION_PHRASE,
    )

    report = write_lsr_v2_paper_supervised_bridge_report(tmp_path, settings)
    events = load_lsr_v2_paper_supervised_bridge_events(tmp_path, settings)
    runtime_event = prepare_lsr_v2_runtime_bridge_event(events[0])

    assert report["would_route_count"] == 1
    assert report["would_submit_count"] == 0
    assert runtime_event["would_route"] is True
    assert runtime_event["would_submit"] is False
    assert runtime_event["blocked_reason"] == "paper_supervised_bridge_fail_closed"


def test_once_console_summary_includes_lsr_v2_bridge_footer_lines() -> None:
    lines = build_paper_once_console_summary_lines(
        {"cycle_id": "pc_1", "scanned": 4, "signals": 0, "orders": 0, "open_positions": 0},
        lsr_v2_bridge={
            "decision": "LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC",
            "bridge_events": 12,
            "candidate_ready_events": 12,
            "would_route_count": 0,
            "would_submit_count": 0,
            "orders_submitted_by_lsr_v2_bridge": 0,
            "positions_opened_by_lsr_v2_bridge": 0,
        },
    )

    assert "lsr_v2_bridge_decision=LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC" in lines
    assert "lsr_v2_bridge_events=12" in lines
    assert "lsr_v2_candidate_ready_events=12" in lines
    assert "lsr_v2_would_route_count=0" in lines
    assert "lsr_v2_would_submit_count=0" in lines
    assert "orders_submitted_by_lsr_v2_bridge=0" in lines
    assert "positions_opened_by_lsr_v2_bridge=0" in lines
