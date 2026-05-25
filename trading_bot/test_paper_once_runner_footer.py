from __future__ import annotations

import io
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_once_runner_footer import print_runner_once_footer_from_events


def test_runner_once_footer_prints_completion_and_no_signal() -> None:
    # Test 1 — Print latest CYCLE_COMPLETED
    with tempfile.TemporaryDirectory() as tmpdir:
        events_file = Path(tmpdir) / "paper_events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(
                '{"event_type":"CYCLE_COMPLETED","cycle_id":"pc_test","scanned":4,"signals":0,"orders":0,"open_positions":0,"errors":0,"elapsed_seconds":10.5,"ts":"2026-05-24T00:00:10+00:00"}\n'
            )

        stream = io.StringIO()
        res = print_runner_once_footer_from_events(events_file, stream=stream)
        assert res is True
        output = stream.getvalue()
        assert "[PAPER CYCLE COMPLETED]" in output
        assert "cycle_id=pc_test" in output
        assert "scanned=4" in output
        assert "orders=0" in output
        assert "errors=0" in output
        assert "[PAPER ONCE RESULT] NO_SIGNAL" in output


def test_runner_once_footer_integrates_runtime_audit() -> None:
    # Test 2 — Integrate runtime audit counts
    with tempfile.TemporaryDirectory() as tmpdir:
        events_file = Path(tmpdir) / "paper_events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(
                '{"event_type":"CYCLE_COMPLETED","cycle_id":"pc_test","scanned":4,"signals":0,"orders":0,"open_positions":0,"errors":0,"elapsed_seconds":10.5,"ts":"2026-05-24T00:00:10+00:00"}\n'
            )
            for _ in range(4):
                f.write(
                    '{"event_type":"GUARDED_PAPER_RUNTIME_AUDIT","cycle_id":"pc_test","accepted_diagnostic":false,"ts":"2026-05-24T00:00:11+00:00"}\n'
                )

        stream = io.StringIO()
        res = print_runner_once_footer_from_events(events_file, stream=stream)
        assert res is True
        output = stream.getvalue()
        assert "runtime_audit_events=4" in output
        assert "runtime_accepts_diagnostic=0" in output
        assert "runtime_rejects=4" in output


def test_runner_once_footer_integrates_routing_bridge() -> None:
    # Test 3 — Integrate routing bridge counts
    with tempfile.TemporaryDirectory() as tmpdir:
        events_file = Path(tmpdir) / "paper_events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(
                '{"event_type":"CYCLE_COMPLETED","cycle_id":"pc_test","scanned":4,"signals":0,"orders":0,"open_positions":0,"errors":0,"elapsed_seconds":10.5,"ts":"2026-05-24T00:00:10+00:00"}\n'
            )
            for _ in range(4):
                f.write(
                    '{"event_type":"GUARDED_PAPER_ROUTING_BRIDGE_AUDIT","cycle_id":"pc_test","would_route":false,"would_submit":false,"orders_submitted_by_bridge":0,"positions_opened_by_bridge":0,"ts":"2026-05-24T00:00:11+00:00"}\n'
                )

        stream = io.StringIO()
        res = print_runner_once_footer_from_events(events_file, stream=stream)
        assert res is True
        output = stream.getvalue()
        assert "routing_bridge_events=4" in output
        assert "would_route_count=0" in output
        assert "would_submit_count=0" in output
        assert "orders_submitted_by_bridge=0" in output
        assert "positions_opened_by_bridge=0" in output


def test_runner_once_footer_ignores_old_cycles() -> None:
    # Test 4 — If CYCLE_COMPLETED.ts < started_at, returns False and does not print
    with tempfile.TemporaryDirectory() as tmpdir:
        events_file = Path(tmpdir) / "paper_events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(
                '{"event_type":"CYCLE_COMPLETED","cycle_id":"pc_test","scanned":4,"signals":0,"orders":0,"open_positions":0,"errors":0,"elapsed_seconds":10.5,"ts":"2026-05-24T00:00:10+00:00"}\n'
            )

        stream = io.StringIO()
        started_at = datetime(2026, 5, 24, 0, 0, 15, tzinfo=timezone.utc)
        res = print_runner_once_footer_from_events(events_file, started_at=started_at, stream=stream)
        assert res is False
        assert stream.getvalue() == ""


def test_runner_once_footer_tolerates_corrupt_lines() -> None:
    # Test 5 — Corrupt lines are ignored without crashing
    with tempfile.TemporaryDirectory() as tmpdir:
        events_file = Path(tmpdir) / "paper_events.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write("corrupted line 1\n")
            f.write(
                '{"event_type":"CYCLE_COMPLETED","cycle_id":"pc_test","scanned":4,"signals":0,"orders":0,"open_positions":0,"errors":0,"elapsed_seconds":10.5,"ts":"2026-05-24T00:00:10+00:00"}\n'
            )
            f.write("corrupted line 2\n")

        stream = io.StringIO()
        res = print_runner_once_footer_from_events(events_file, stream=stream)
        assert res is True
        output = stream.getvalue()
        assert "[PAPER CYCLE COMPLETED]" in output


def test_runner_once_footer_returns_false_if_file_absent() -> None:
    # Test 6 — Absent file returns False
    res = print_runner_once_footer_from_events("this_file_does_not_exist.jsonl")
    assert res is False


if __name__ == "__main__":
    test_runner_once_footer_prints_completion_and_no_signal()
    test_runner_once_footer_integrates_runtime_audit()
    test_runner_once_footer_integrates_routing_bridge()
    test_runner_once_footer_ignores_old_cycles()
    test_runner_once_footer_tolerates_corrupt_lines()
    test_runner_once_footer_returns_false_if_file_absent()
    print("Paper once runner footer tests passed.")
