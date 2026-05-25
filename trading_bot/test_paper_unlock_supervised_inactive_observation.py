from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.paper_unlock_observation import (
    CYCLE_COMPLETED_EVENT_TYPE,
    RUNTIME_AUDIT_EVENT_TYPE,
    ROUTING_BRIDGE_EVENT_TYPE,
    CANDIDATE_AUDIT_EVENT_TYPE,
    HANDOFF_DRY_RUN_EVENT_TYPE,
    SUPERVISED_EXECUTION_EVENT_TYPE,
)
from core.paper_unlock_supervised_inactive_observation import (
    PaperUnlockSupervisedInactiveObservationSettings,
    build_paper_unlock_supervised_inactive_observation_report,
    write_paper_unlock_supervised_inactive_observation_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _base_rows() -> list[dict]:
    return [
        {"event_type": RUNTIME_AUDIT_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:01+00:00", "accepted_diagnostic": False, "reject_reasons": ["operator_enable_not_active"]},
        {"event_type": ROUTING_BRIDGE_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:02+00:00", "would_route": False, "would_submit": False, "orders_submitted_by_bridge": 0, "positions_opened_by_bridge": 0, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
        {"event_type": CYCLE_COMPLETED_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:10+00:00", "scanned": 4, "signals": 0, "orders": 0, "open_positions": 0, "errors": 0},
    ]


def test_supervised_inactive_observation_passes_without_supervised_events() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_jsonl(base / "paper_events.jsonl", _base_rows())
        report = build_paper_unlock_supervised_inactive_observation_report(base, settings=PaperUnlockSupervisedInactiveObservationSettings(max_event_lines=1000))
        assert report["prompt"] == "29.4.4s-OBS"
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "PAPER_SUPERVISED_INACTIVE_OBSERVATION_READY_DIAGNOSTIC"
        assert report["decision"]["supervised_submit_allowed_count"] == 0
        assert report["decision"]["orders_submitted"] == 0
        assert report["inactive_safety_checks"]["operator_enable_inactive"] is True


def test_supervised_inactive_observation_tracks_candidate_exposure_but_blocks_submit() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rows = _base_rows()[:-1] + [
            {"event_type": CANDIDATE_AUDIT_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:03+00:00", "candidate_ready": True, "orders_submitted_by_candidate_audit": 0, "positions_opened_by_candidate_audit": 0, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
            {"event_type": HANDOFF_DRY_RUN_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:04+00:00", "candidate_ready": True, "would_create_order": True, "broker_submit_called": False, "orders_submitted_by_handoff": 0, "positions_opened_by_handoff": 0, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
            {"event_type": SUPERVISED_EXECUTION_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:05+00:00", "candidate_ready": True, "would_create_order": True, "operator_enable": False, "operator_confirmation_ok": False, "supervised_submit_allowed": False, "broker_submit_called": False, "orders_submitted_by_supervised": 0, "positions_opened_by_supervised": 0, "blocked_reasons": ["operator_enable_not_active"], "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
            _base_rows()[-1],
        ]
        _write_jsonl(base / "paper_events.jsonl", rows)
        report = build_paper_unlock_supervised_inactive_observation_report(base, settings=PaperUnlockSupervisedInactiveObservationSettings(max_event_lines=1000))
        assert report["status"] == "PASS"
        assert report["decision"]["candidate_ready_count"] == 1
        assert report["decision"]["would_create_order_count"] == 1
        assert report["decision"]["supervised_execution_events"] == 1
        assert report["candidate_exposure_monitor"]["supervised_blocked_reason_counts"]["operator_enable_not_active"] == 1


def test_supervised_inactive_observation_warns_on_supervised_submit() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rows = _base_rows()[:-1] + [
            {"event_type": SUPERVISED_EXECUTION_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:05+00:00", "supervised_submit_allowed": True, "broker_submit_called": True, "orders_submitted_by_supervised": 1, "positions_opened_by_supervised": 1, "operational_unlock_allowed": False, "live_allowed": False, "testnet_allowed": False, "exchange_broker_allowed": False},
            {"event_type": CYCLE_COMPLETED_EVENT_TYPE, "cycle_id": "pc_sobs", "ts": "2026-05-25T00:00:10+00:00", "scanned": 4, "signals": 1, "orders": 1, "open_positions": 1, "errors": 0},
        ]
        _write_jsonl(base / "paper_events.jsonl", rows)
        report = build_paper_unlock_supervised_inactive_observation_report(base, settings=PaperUnlockSupervisedInactiveObservationSettings(max_event_lines=1000))
        assert report["status"] == "WARN"
        assert report["inactive_safety_checks"]["supervised_submit_allowed_zero"] is False
        out = write_paper_unlock_supervised_inactive_observation_report(base, settings=PaperUnlockSupervisedInactiveObservationSettings(max_event_lines=1000))
        assert (base / "paper_unlock_supervised_inactive_observation_report.json").exists()
        assert out["prompt"] == "29.4.4s-OBS"


if __name__ == "__main__":
    test_supervised_inactive_observation_passes_without_supervised_events()
    test_supervised_inactive_observation_tracks_candidate_exposure_but_blocks_submit()
    test_supervised_inactive_observation_warns_on_supervised_submit()
    print("Paper unlock supervised inactive observation tests passed.")
