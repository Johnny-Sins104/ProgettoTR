from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_runtime_audit import (
    RUNTIME_EVENT_TYPE,
    RuntimePaperOrderAuditSettings,
    build_guarded_runtime_audit_event,
    write_paper_unlock_runtime_audit_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_guarded_runtime_audit_event_rejects_wait_state() -> None:
    state = {
        "status": "PASS",
        "decision": {"status": "GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED", "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"},
        "paper_orders_enabled": True,
        "paper_unlock_experiment_allowed": True,
        "manual_activation_allowed": True,
        "automatic_activation_allowed": False,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }
    event = build_guarded_runtime_audit_event(
        guarded_enable_state=state,
        cycle_id="pc_test",
        symbol="ETH/USDT",
        candle_ts="2026-01-01 00:00:00+00:00",
        mode="paper",
        signal_diagnostic={"intended_side": "BUY", "dominant_filter": "RANGE_POSITION_FILTERED"},
        scenario_diagnostic={"directional_bias": "BUY", "scenario": "BUY_REJECTION_CANDIDATE"},
        pattern_diagnostic={"pattern_bias": "BUY", "pattern_score": 65.0},
        structure_diagnostic={"map_score": 70.0, "confirmation_summary": "PRICE_IN_DEMAND_WAIT_CONFIRMATION", "confirmation_close": False},
        legacy_unlock_decision={"profile": "BTC_ONLY_40_Q60", "accepted": False},
    )
    assert event["event_type"] == RUNTIME_EVENT_TYPE
    assert event["paper_orders_enabled"] is True
    assert event["accepted_diagnostic"] is False
    assert "structure_state_not_confirmation:WAIT" in event["reject_reasons"]
    assert event["routing_enabled"] is False


def test_guarded_runtime_audit_event_can_be_diagnostic_eligible() -> None:
    state = {
        "status": "PASS",
        "decision": {"status": "GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED", "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"},
        "paper_orders_enabled": True,
        "paper_unlock_experiment_allowed": True,
        "manual_activation_allowed": True,
        "automatic_activation_allowed": False,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }
    event = build_guarded_runtime_audit_event(
        guarded_enable_state=state,
        cycle_id="pc_test",
        symbol="BTC/USDT",
        candle_ts="2026-01-01 00:00:00+00:00",
        mode="paper",
        signal_diagnostic={"intended_side": "SELL", "dominant_filter": "META_PROB_LOW"},
        scenario_diagnostic={"directional_bias": "SELL", "scenario": "SELL_BREAKDOWN_CANDIDATE"},
        pattern_diagnostic={"pattern_bias": "SELL", "pattern_score": 70.0},
        structure_diagnostic={"map_score": 70.0, "confirmation_summary": "BEARISH_BOS", "confirmation_close": True},
        legacy_unlock_decision={"profile": "BTC_ONLY_40_Q60", "accepted": False},
    )
    assert event["accepted_diagnostic"] is True
    assert event["primary_reject_reason"] == "eligible_diagnostic_only"
    assert event["orders_submitted_by_audit"] == 0


def test_runtime_audit_report_reads_latest_cycle_and_legacy_profile() -> None:
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
        events = [
            {"event_type": "PAPER_UNLOCK_EVALUATED", "cycle_id": "pc_test", "symbol": "BTC/USDT", "reason": "filter_not_allowed:RANGE_POSITION_FILTERED", "decision": {"profile": "BTC_ONLY_40_Q60", "accepted": False}},
            {"event_type": RUNTIME_EVENT_TYPE, "cycle_id": "pc_test", "symbol": "BTC/USDT", "accepted_diagnostic": False, "reject_reasons": ["map_score_outside_65_79"], "runtime_structure_state": "NO_STRUCTURE", "map_score_ok": False, "operator_state_ok": True, "routing_enabled": False},
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_test", "scanned": 1, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0, "no_signal": 1},
        ]
        (base / "paper_events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        _write_json(base / "paper_status.json", {"mode": "paper"})
        report = write_paper_unlock_runtime_audit_report(base, RuntimePaperOrderAuditSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "RUNTIME_PAPER_ORDER_AUDIT_READY_DIAGNOSTIC"
        assert report["legacy_unlock_audit"]["legacy_profile_counts"]["BTC_ONLY_40_Q60"] == 1
        assert report["runtime_profile_audit"]["runtime_audit_present"] is True
        assert report["orders_submitted"] == 0
        assert (base / "paper_unlock_runtime_audit_report.json").exists()


if __name__ == "__main__":
    test_guarded_runtime_audit_event_rejects_wait_state()
    test_guarded_runtime_audit_event_can_be_diagnostic_eligible()
    test_runtime_audit_report_reads_latest_cycle_and_legacy_profile()
    print("Paper unlock runtime audit tests passed.")
