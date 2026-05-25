from __future__ import annotations

import json
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_supervised_execution import (
    PaperUnlockSupervisedExecutionSettings,
    build_paper_supervised_execution_event,
    write_paper_unlock_supervised_execution_report,
)


def _handoff(*, ready: bool = True, would_create: bool = True, controls: bool = True) -> dict:
    return {
        "event_type": "PAPER_ORDER_HANDOFF_DRY_RUN",
        "cycle_id": "pc_test",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "mode": "paper",
        "candidate_ready": ready,
        "would_create_order": would_create,
        "paper_orders_enabled": controls,
        "paper_unlock_experiment_allowed": controls,
        "manual_activation_allowed": controls,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "position_size": 1.0,
        "notional": 100.0,
        "risk_amount": 1.0,
    }


def test_supervised_event_blocks_without_operator_confirmation() -> None:
    settings = PaperUnlockSupervisedExecutionSettings(enabled=True, operator_enable=False, operator_confirmation="")
    event = build_paper_supervised_execution_event(settings=settings, handoff_event=_handoff(), open_positions_count=0)
    assert event["event_type"] == "PAPER_SUPERVISED_ORDER_EXECUTION"
    assert event["supervised_submit_allowed"] is False
    assert "operator_enable_not_active" in event["blocked_reasons"]
    assert event["orders_submitted_by_supervised"] == 0
    assert event["live_allowed"] is False
    assert event["exchange_broker_allowed"] is False


def test_supervised_event_allows_only_with_operator_controls() -> None:
    settings = PaperUnlockSupervisedExecutionSettings(
        enabled=True,
        operator_enable=True,
        operator_confirmation="I_UNDERSTAND_PAPER_ONLY",
    )
    event = build_paper_supervised_execution_event(settings=settings, handoff_event=_handoff(), open_positions_count=0)
    assert event["operator_authorized"] is True
    assert event["supervised_submit_allowed"] is True
    assert event["would_submit_to_paper_broker"] is True
    assert event["blocked_reasons"] == []


def test_supervised_event_rejects_when_handoff_not_ready() -> None:
    settings = PaperUnlockSupervisedExecutionSettings(
        enabled=True,
        operator_enable=True,
        operator_confirmation="I_UNDERSTAND_PAPER_ONLY",
    )
    event = build_paper_supervised_execution_event(settings=settings, handoff_event=_handoff(ready=False), open_positions_count=0)
    assert event["supervised_submit_allowed"] is False
    assert "candidate_ready_false" in event["blocked_reasons"]


def test_supervised_report_passes_without_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = write_paper_unlock_supervised_execution_report(tmp, PaperUnlockSupervisedExecutionSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["supervised_execution_events"] == 0
        assert report["decision"]["broker_submit_called_count"] == 0


def test_supervised_report_counts_submitted_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        event = build_paper_supervised_execution_event(
            settings=PaperUnlockSupervisedExecutionSettings(
                enabled=True,
                operator_enable=True,
                operator_confirmation="I_UNDERSTAND_PAPER_ONLY",
            ),
            handoff_event=_handoff(),
            open_positions_count=0,
            broker_submit_called=True,
            order_submitted=True,
            position_opened=True,
            order_id="po_test",
        )
        (base / "paper_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        report = write_paper_unlock_supervised_execution_report(base, PaperUnlockSupervisedExecutionSettings())
        assert report["status"] == "PASS"
        assert report["decision"]["broker_submit_called_count"] == 1
        assert report["decision"]["orders_submitted_by_supervised"] == 1
        assert report["decision"]["positions_opened_by_supervised"] == 1


if __name__ == "__main__":
    test_supervised_event_blocks_without_operator_confirmation()
    test_supervised_event_allows_only_with_operator_controls()
    test_supervised_event_rejects_when_handoff_not_ready()
    test_supervised_report_passes_without_events()
    test_supervised_report_counts_submitted_event()
    print("Paper unlock supervised execution tests passed.")
