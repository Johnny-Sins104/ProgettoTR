from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_routing_bridge import (
    EVENT_TYPE,
    GuardedPaperRoutingBridgeSettings,
    build_guarded_paper_routing_bridge_event,
    write_paper_unlock_routing_bridge_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _eligible_runtime_event() -> dict:
    return {
        "event_type": "GUARDED_PAPER_RUNTIME_AUDIT",
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "candle_ts": "2026-01-01 00:00:00+00:00",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "side": "BUY",
        "accepted_diagnostic": True,
        "paper_orders_enabled": True,
        "paper_unlock_experiment_allowed": True,
        "manual_activation_allowed": True,
        "automatic_activation_allowed": False,
        "operational_unlock_allowed": False,
        "mode": "paper",
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "map_score": 70.0,
        "runtime_structure_state": "CONFIRMATION",
        "open_positions_count": 0,
    }


def test_routing_bridge_rejects_non_accepted_diagnostic() -> None:
    runtime_event = _eligible_runtime_event()
    runtime_event["accepted_diagnostic"] = False
    event = build_guarded_paper_routing_bridge_event(runtime_audit_event=runtime_event)
    assert event["event_type"] == EVENT_TYPE
    assert event["would_route"] is False
    assert event["would_submit"] is False
    assert "accepted_diagnostic_false" in event["blocked_reasons"]
    assert event["orders_submitted_by_bridge"] == 0


def test_routing_bridge_marks_eligible_candidate_without_submitting_order() -> None:
    event = build_guarded_paper_routing_bridge_event(runtime_audit_event=_eligible_runtime_event())
    assert event["would_route"] is True
    assert event["would_submit"] is True
    assert event["routing_mode"] == "paper_only"
    assert event["submission_mode"] == "simulation_only"
    assert event["orders_submitted_by_bridge"] == 0
    assert event["live_blocked"] is True
    assert event["testnet_blocked"] is True
    assert event["exchange_broker_blocked"] is True


def test_routing_bridge_report_reads_latest_cycle_and_stays_paper_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_json(base / "paper_unlock_guarded_enable_report.json", {
            "status": "PASS",
            "decision": {"status": "GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED", "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1", "enable_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE"},
            "paper_orders_enabled": True,
            "paper_unlock_experiment_allowed": True,
            "manual_activation_allowed": True,
            "automatic_activation_allowed": False,
            "operational_unlock_allowed": False,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
        })
        runtime_event = _eligible_runtime_event()
        bridge_event = build_guarded_paper_routing_bridge_event(runtime_audit_event=runtime_event)
        events = [
            runtime_event,
            bridge_event,
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0, "no_signal": 1},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        _write_json(base / "paper_status.json", {"mode": "paper"})
        report = write_paper_unlock_routing_bridge_report(base, GuardedPaperRoutingBridgeSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "ROUTING_BRIDGE_AUDIT_READY_DIAGNOSTIC"
        assert report["decision"]["would_submit_count"] == 1
        assert report["orders_submitted_by_bridge"] == 0
        assert report["orders_submitted"] == 0
        assert report["operational_unlock_allowed"] is False
        assert report["live_allowed"] is False
        assert (base / "paper_unlock_routing_bridge_report.json").exists()


if __name__ == "__main__":
    test_routing_bridge_rejects_non_accepted_diagnostic()
    test_routing_bridge_marks_eligible_candidate_without_submitting_order()
    test_routing_bridge_report_reads_latest_cycle_and_stays_paper_only()
    print("Paper unlock routing bridge tests passed.")
