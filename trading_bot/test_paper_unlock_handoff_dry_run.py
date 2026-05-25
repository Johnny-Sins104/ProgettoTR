from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_candidate_audit import EVENT_TYPE as CANDIDATE_EVENT_TYPE
from core.paper_unlock_handoff_dry_run import (
    EVENT_TYPE,
    PaperOrderHandoffDryRunSettings,
    build_paper_order_handoff_dry_run_event,
    write_paper_unlock_handoff_dry_run_report,
)


def _candidate_event(*, ready: bool = True) -> dict:
    return {
        "event_type": CANDIDATE_EVENT_TYPE,
        "prompt": "29.4.4q",
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "candle_ts": "2026-01-01 00:00:00+00:00",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "side": "BUY",
        "mode": "paper",
        "paper_only_mode": True,
        "routing_mode": "paper_only",
        "submission_mode": "candidate_audit_only",
        "audit_only": True,
        "candidate_ready": bool(ready),
        "paper_orders_enabled": True,
        "paper_unlock_experiment_allowed": True,
        "manual_activation_allowed": True,
        "automatic_activation_allowed": False,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "entry_price": 100.0,
        "stop_loss": 96.0,
        "take_profit": 108.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 0.625,
        "notional": 62.5,
        "max_positions": 1,
        "open_positions_count": 0,
        "orders_submitted_by_candidate_audit": 0,
        "positions_opened_by_candidate_audit": 0,
    }


def test_handoff_dry_run_builds_would_create_order_without_submission() -> None:
    event = build_paper_order_handoff_dry_run_event(candidate_event=_candidate_event(ready=True))
    assert event["event_type"] == EVENT_TYPE
    assert event["candidate_ready"] is True
    assert event["would_create_order"] is True
    assert event["would_submit_to_paper_broker"] is False
    assert event["broker_submit_called"] is False
    assert event["paper_broker_adapter"] == "PaperBrokerAdapter"
    assert event["exchange_broker_allowed"] is False
    assert event["orders_submitted_by_handoff"] == 0
    assert event["positions_opened_by_handoff"] == 0


def test_handoff_dry_run_rejects_when_candidate_not_ready() -> None:
    event = build_paper_order_handoff_dry_run_event(candidate_event=_candidate_event(ready=False))
    assert event["would_create_order"] is False
    assert "candidate_ready_false" in event["blocked_reasons"]
    assert event["orders_submitted_by_handoff"] == 0


def test_handoff_report_passes_without_ready_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        events = [
            _candidate_event(ready=False),
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        (base / "paper_status.json").write_text(json.dumps({"mode": "paper"}), encoding="utf-8")
        report = write_paper_unlock_handoff_dry_run_report(base, PaperOrderHandoffDryRunSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["candidate_ready_count"] == 0
        assert report["decision"]["handoff_dry_run_events"] == 0
        assert report["decision"]["handoff_coverage_ok"] is True
        assert report["orders_submitted_by_handoff"] == 0
        assert report["positions_opened_by_handoff"] == 0


def test_handoff_report_covers_ready_candidate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        candidate = _candidate_event(ready=True)
        handoff = build_paper_order_handoff_dry_run_event(candidate_event=candidate)
        events = [
            candidate,
            handoff,
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        (base / "paper_status.json").write_text(json.dumps({"mode": "paper"}), encoding="utf-8")
        report = write_paper_unlock_handoff_dry_run_report(base, PaperOrderHandoffDryRunSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["candidate_ready_count"] == 1
        assert report["decision"]["handoff_dry_run_events"] == 1
        assert report["decision"]["would_create_order_count"] == 1
        assert report["decision"]["orders_submitted_by_handoff"] == 0
        assert report["operational_unlock_allowed"] is False
        assert report["live_allowed"] is False
        assert (base / "paper_unlock_handoff_dry_run_report.json").exists()


if __name__ == "__main__":
    test_handoff_dry_run_builds_would_create_order_without_submission()
    test_handoff_dry_run_rejects_when_candidate_not_ready()
    test_handoff_report_passes_without_ready_candidates()
    test_handoff_report_covers_ready_candidate()
    print("Paper unlock handoff dry-run tests passed.")
