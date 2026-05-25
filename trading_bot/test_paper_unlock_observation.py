from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.paper_unlock_observation import (
    CANDIDATE_AUDIT_EVENT_TYPE,
    HANDOFF_DRY_RUN_EVENT_TYPE,
    CYCLE_COMPLETED_EVENT_TYPE,
    ROUTING_BRIDGE_EVENT_TYPE,
    RUNTIME_AUDIT_EVENT_TYPE,
    PaperUnlockObservationSettings,
    build_paper_unlock_observation_report,
    write_paper_unlock_observation_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_observation_report_aggregates_cycle_runtime_bridge_candidate() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rows = [
            {"event_type": RUNTIME_AUDIT_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:01+00:00", "accepted_diagnostic": False, "map_score": 45, "runtime_structure_state": "WAIT", "side": "BUY", "reject_reasons": ["map_score_outside_65_79"]},
            {"event_type": RUNTIME_AUDIT_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:02+00:00", "accepted_diagnostic": False, "map_score": 50, "runtime_structure_state": "NO_STRUCTURE", "side": "HOLD", "reject_reasons": ["structure_state_not_confirmation:NO_STRUCTURE"]},
            {"event_type": ROUTING_BRIDGE_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:03+00:00", "would_route": False, "would_submit": False, "orders_submitted_by_bridge": 0, "positions_opened_by_bridge": 0, "blocked_reasons": ["accepted_diagnostic_false"], "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False, "map_score": 45, "runtime_structure_state": "WAIT", "side": "BUY"},
            {"event_type": ROUTING_BRIDGE_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:04+00:00", "would_route": False, "would_submit": False, "orders_submitted_by_bridge": 0, "positions_opened_by_bridge": 0, "blocked_reasons": ["accepted_diagnostic_false"], "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False, "map_score": 50, "runtime_structure_state": "NO_STRUCTURE", "side": "HOLD"},
            {"event_type": CANDIDATE_AUDIT_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:05+00:00", "candidate_ready": False, "blocked_reasons": ["candidate_not_ready"], "orders_submitted_by_candidate_audit": 0, "positions_opened_by_candidate_audit": 0, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False, "side": "BUY", "submission_mode": "candidate_audit_only"},
            {"event_type": HANDOFF_DRY_RUN_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:06+00:00", "candidate_ready": False, "would_create_order": False, "broker_submit_called": False, "orders_submitted_by_handoff": 0, "positions_opened_by_handoff": 0, "blocked_reasons": ["candidate_ready_false"], "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False, "side": "BUY", "submission_mode": "handoff_dry_run_only", "paper_broker_adapter": "PaperBrokerAdapter"},
            {"event_type": CYCLE_COMPLETED_EVENT_TYPE, "cycle_id": "pc_obs", "ts": "2026-05-24T00:00:10+00:00", "scanned": 4, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0, "elapsed_seconds": 11.0},
        ]
        _write_jsonl(base / "paper_events.jsonl", rows)
        report = build_paper_unlock_observation_report(base, settings=PaperUnlockObservationSettings(max_event_lines=1000))
        decision = report["decision"]
        assert report["status"] == "PASS"
        assert decision["latest_cycle_id"] == "pc_obs"
        assert decision["completed_cycle_count"] == 1
        assert decision["runtime_audit_events"] == 2
        assert decision["runtime_accepts_diagnostic"] == 0
        assert decision["routing_bridge_events"] == 2
        assert decision["would_submit_count"] == 0
        assert decision["candidate_order_audit_events"] == 1
        assert decision["handoff_dry_run_events"] == 1
        assert decision["would_create_order_count"] == 0
        assert decision["broker_submit_called_count"] == 0
        assert decision["orders_submitted_by_handoff"] == 0
        assert decision["positions_opened_by_handoff"] == 0
        assert decision["orders_submitted"] == 0
        assert decision["positions_opened"] == 0
        assert report["safety_checks"]["live_blocked"] is True
        assert report["safety_checks"]["handoff_broker_submit_not_called"] is True
        assert report["routing_bridge"]["blocked_reason_counts"]["accepted_diagnostic_false"] == 2
        assert report["handoff_dry_run"]["blocked_reason_counts"]["candidate_ready_false"] == 1


def test_observation_report_window_filters_old_cycles() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rows = [
            {"event_type": CYCLE_COMPLETED_EVENT_TYPE, "cycle_id": "old", "ts": "2026-05-24T00:00:00+00:00", "scanned": 4, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
            {"event_type": RUNTIME_AUDIT_EVENT_TYPE, "cycle_id": "new", "ts": "2026-05-24T01:00:01+00:00", "accepted_diagnostic": False},
            {"event_type": ROUTING_BRIDGE_EVENT_TYPE, "cycle_id": "new", "ts": "2026-05-24T01:00:02+00:00", "would_submit": False, "orders_submitted_by_bridge": 0, "positions_opened_by_bridge": 0, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
            {"event_type": CYCLE_COMPLETED_EVENT_TYPE, "cycle_id": "new", "ts": "2026-05-24T01:00:10+00:00", "scanned": 4, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
        ]
        _write_jsonl(base / "paper_events.jsonl", rows)
        report = build_paper_unlock_observation_report(
            base,
            started_at=datetime(2026, 5, 24, 0, 30, tzinfo=timezone.utc),
            settings=PaperUnlockObservationSettings(max_event_lines=1000),
        )
        assert report["decision"]["latest_cycle_id"] == "new"
        assert report["decision"]["completed_cycle_count"] == 1


def test_observation_report_handles_missing_and_corrupt_lines() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "paper_events.jsonl").write_text("not-json\n{}\n", encoding="utf-8")
        report = build_paper_unlock_observation_report(base, settings=PaperUnlockObservationSettings(max_event_lines=1000))
        assert report["status"] == "WARN"
        assert report["decision"]["completed_cycle_count"] == 0
        out = write_paper_unlock_observation_report(base, settings=PaperUnlockObservationSettings(max_event_lines=1000))
        assert (base / "paper_unlock_4h_observation_report.json").exists()
        assert out["prompt"] == "29.4.4r-OBS"


if __name__ == "__main__":
    test_observation_report_aggregates_cycle_runtime_bridge_candidate()
    test_observation_report_window_filters_old_cycles()
    test_observation_report_handles_missing_and_corrupt_lines()
    print("Paper unlock observation tests passed.")
