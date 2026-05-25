from __future__ import annotations

import io
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_once_console_summary import build_paper_once_console_summary_lines, print_paper_once_console_summary


def test_once_console_summary_prints_completion_and_no_signal() -> None:
    lines = build_paper_once_console_summary_lines(
        {
            "cycle_id": "pc_test",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
            "errors": 0,
            "no_signal": 4,
            "elapsed_seconds": 1.23456,
        },
        runtime_audit={
            "paper_orders_enabled": True,
            "paper_unlock_experiment_allowed": True,
            "operational_unlock_allowed": False,
            "decision": {
                "runtime_audit_events": 4,
                "runtime_accepts_diagnostic": 0,
                "runtime_rejects": 4,
            },
        },
        routing_bridge={
            "decision": {
                "routing_bridge_events": 4,
                "would_route_count": 0,
                "would_submit_count": 0,
                "orders_submitted_by_bridge": 0,
                "positions_opened_by_bridge": 0,
            }
        },
    )
    joined = "\n".join(lines)
    assert "[PAPER CYCLE COMPLETED]" in joined
    assert "cycle_id=pc_test" in joined
    assert "scanned=4" in joined
    assert "orders=0" in joined
    assert "paper_orders_enabled=true" in joined
    assert "operational_unlock_allowed=false" in joined
    assert "runtime_audit_events=4" in joined
    assert "routing_bridge_events=4" in joined
    assert "would_submit_count=0" in joined
    assert "positions_opened_by_bridge=0" in joined
    assert "[PAPER ONCE RESULT] NO_SIGNAL" in joined
    assert "reason=all assets rejected by filters" in joined


def test_once_console_summary_does_not_invent_orders() -> None:
    lines = build_paper_once_console_summary_lines(
        {"cycle_id": "pc_test", "scanned": 1, "signals": 1, "orders": 0, "open_positions": 0, "errors": 0},
        runtime_audit={"operational_unlock_allowed": False, "decision": {}},
    )
    joined = "\n".join(lines)
    assert "[PAPER ONCE RESULT] SIGNAL_NO_ORDER" in joined
    assert "orders=0" in joined


class FlushTrackingStringIO(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def test_once_console_summary_flushes_stdout_footer() -> None:
    stream = FlushTrackingStringIO()
    print_paper_once_console_summary(
        {
            "cycle_id": "pc_flush",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
            "errors": 0,
            "no_signal": 4,
            "elapsed_seconds": 1.0,
        },
        runtime_audit={"operational_unlock_allowed": False, "decision": {"runtime_audit_events": 4}},
        routing_bridge={"decision": {"routing_bridge_events": 4, "would_submit_count": 0}},
        stream=stream,
    )
    output = stream.getvalue()
    assert "[PAPER CYCLE COMPLETED]" in output
    assert "cycle_id=pc_flush" in output
    assert "[PAPER ONCE RESULT] NO_SIGNAL" in output
    assert stream.flush_count >= 1


if __name__ == "__main__":
    test_once_console_summary_prints_completion_and_no_signal()
    test_once_console_summary_does_not_invent_orders()
    test_once_console_summary_flushes_stdout_footer()
    print("Paper once console summary tests passed.")
