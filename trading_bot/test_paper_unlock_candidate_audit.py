from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_candidate_audit import (
    EVENT_TYPE,
    GuardedPaperOrderCandidateAuditSettings,
    build_guarded_paper_order_candidate_audit_event,
    write_paper_unlock_candidate_audit_report,
)
from core.paper_unlock_routing_bridge import EVENT_TYPE as BRIDGE_EVENT_TYPE


def _bridge_event(*, would_submit: bool = True) -> dict:
    return {
        "event_type": BRIDGE_EVENT_TYPE,
        "prompt": "29.4.4p",
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
        "paper_only_mode": True,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "would_route": bool(would_submit),
        "would_submit": bool(would_submit),
        "routing_mode": "paper_only",
        "submission_mode": "simulation_only",
        "risk_per_trade_pct": 0.0025,
        "max_positions": 1,
        "open_positions_count": 0,
        "orders_submitted_by_bridge": 0,
        "positions_opened_by_bridge": 0,
    }


def test_candidate_audit_builds_ready_candidate_without_submitting_order() -> None:
    event = build_guarded_paper_order_candidate_audit_event(
        routing_bridge_event=_bridge_event(would_submit=True),
        entry_price=100.0,
        atr=2.0,
        account_balance=1000.0,
        equity=1000.0,
        open_positions_count=0,
    )
    assert event["event_type"] == EVENT_TYPE
    assert event["candidate_ready"] is True
    assert event["audit_only"] is True
    assert event["submission_mode"] == "candidate_audit_only"
    assert event["entry_price"] == 100.0
    assert event["stop_loss"] < 100.0
    assert event["take_profit"] > 100.0
    assert event["risk_per_trade_pct"] == 0.0025
    assert event["orders_submitted_by_candidate_audit"] == 0
    assert event["positions_opened_by_candidate_audit"] == 0
    assert event["live_allowed"] is False
    assert event["testnet_allowed"] is False
    assert event["exchange_broker_allowed"] is False


def test_candidate_audit_rejects_when_bridge_would_submit_false() -> None:
    event = build_guarded_paper_order_candidate_audit_event(
        routing_bridge_event=_bridge_event(would_submit=False),
        entry_price=100.0,
        atr=2.0,
        account_balance=1000.0,
        equity=1000.0,
        open_positions_count=0,
    )
    assert event["candidate_ready"] is False
    assert "bridge_would_submit_false" in event["blocked_reasons"]
    assert event["orders_submitted_by_candidate_audit"] == 0


def test_candidate_audit_report_passes_without_would_submit_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        events = [
            _bridge_event(would_submit=False),
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        (base / "paper_status.json").write_text(json.dumps({"mode": "paper"}), encoding="utf-8")
        report = write_paper_unlock_candidate_audit_report(base, GuardedPaperOrderCandidateAuditSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["would_submit_count"] == 0
        assert report["decision"]["candidate_order_audit_events"] == 0
        assert report["decision"]["candidate_coverage_ok"] is True
        assert report["orders_submitted_by_candidate_audit"] == 0
        assert report["positions_opened_by_candidate_audit"] == 0


def test_candidate_audit_report_covers_would_submit_candidate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        bridge = _bridge_event(would_submit=True)
        candidate = build_guarded_paper_order_candidate_audit_event(
            routing_bridge_event=bridge,
            entry_price=100.0,
            atr=2.0,
            account_balance=1000.0,
            equity=1000.0,
            open_positions_count=0,
        )
        events = [
            bridge,
            candidate,
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        (base / "paper_status.json").write_text(json.dumps({"mode": "paper"}), encoding="utf-8")
        report = write_paper_unlock_candidate_audit_report(base, GuardedPaperOrderCandidateAuditSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["would_submit_count"] == 1
        assert report["decision"]["candidate_order_audit_events"] == 1
        assert report["decision"]["candidate_ready_count"] == 1
        assert report["decision"]["orders_submitted_by_candidate_audit"] == 0
        assert report["operational_unlock_allowed"] is False
        assert report["live_allowed"] is False
        assert (base / "paper_unlock_candidate_audit_report.json").exists()


if __name__ == "__main__":
    test_candidate_audit_builds_ready_candidate_without_submitting_order()
    test_candidate_audit_rejects_when_bridge_would_submit_false()
    test_candidate_audit_report_passes_without_would_submit_candidates()
    test_candidate_audit_report_covers_would_submit_candidate()
    print("Paper unlock candidate audit tests passed.")
