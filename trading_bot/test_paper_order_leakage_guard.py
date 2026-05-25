from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.paper_order_leakage_guard import (
    PaperOrderLeakageGuardSettings,
    build_legacy_paper_order_blocked_event,
    should_block_paper_order_attempt,
    summarize_order_leakage_events,
    write_paper_order_leakage_guard_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_guard_blocks_default_legacy_order_attempt() -> None:
    settings = PaperOrderLeakageGuardSettings()
    metadata = {"combination": "ScoreOnly+Meta_OK(p:89.4%,q:81.7)", "cycle_id": "pc_test"}
    assert should_block_paper_order_attempt(settings=settings, metadata=metadata) is True
    event = build_legacy_paper_order_blocked_event(
        settings=settings,
        cycle_id="pc_test",
        symbol="BTC/USDT",
        side="SELL",
        score=8,
        combination="ScoreOnly+Meta_OK(p:89.4%,q:81.7)",
        entry_price=76596.0,
        stop_loss=76753.25,
        take_profit=76281.48,
        qty=0.013056,
        notional=1000.0,
        risk_amount=2.05,
        source_path="legacy_score_meta",
    )
    assert event["event_type"] == "LEGACY_PAPER_ORDER_BLOCKED"
    assert event["would_have_submitted"] is True
    assert event["order_submitted"] is False
    assert event["position_opened"] is False
    assert event["allowed_order_source"] == "NONE"


def test_leakage_report_detects_historical_unauthorized_order_and_position() -> None:
    settings = PaperOrderLeakageGuardSettings(max_event_lines=1000)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rows = [
            {
                "event_type": "PAPER_ORDER_SUBMITTED",
                "ts": "2026-05-24T00:00:01+00:00",
                "cycle_id": "pc_legacy",
                "order_id": "po_1",
                "symbol": "BTC/USDT",
                "side": "SELL",
                "order": {
                    "order_id": "po_1",
                    "symbol": "BTC/USDT",
                    "side": "SELL",
                    "metadata": {"cycle_id": "pc_legacy", "combination": "ScoreOnly+Meta_OK(p:89.4%,q:81.7)"},
                },
            },
            {
                "event_type": "ORDER_FILLED",
                "ts": "2026-05-24T00:00:02+00:00",
                "cycle_id": "pc_legacy",
                "order_id": "po_1",
                "symbol": "BTC/USDT",
                "side": "SELL",
                "order": {
                    "order_id": "po_1",
                    "symbol": "BTC/USDT",
                    "side": "SELL",
                    "metadata": {"cycle_id": "pc_legacy", "combination": "ScoreOnly+Meta_OK(p:89.4%,q:81.7)"},
                },
            },
            {
                "event_type": "POSITION_OPENED",
                "ts": "2026-05-24T00:00:03+00:00",
                "cycle_id": "pc_legacy",
                "position_id": "pp_1",
                "symbol": "BTC/USDT",
                "side": "SELL",
                "position": {
                    "position_id": "pp_1",
                    "symbol": "BTC/USDT",
                    "side": "SELL",
                    "metadata": {"cycle_id": "pc_legacy", "combination": "ScoreOnly+Meta_OK(p:89.4%,q:81.7)"},
                },
            },
            {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_legacy", "orders": 1, "open_positions": 1},
        ]
        _write_jsonl(base / "paper_events.jsonl", rows)
        report = write_paper_order_leakage_guard_report(base, settings)
        decision = report["decision"]
        assert report["status"] == "WARN"
        assert decision["legacy_order_leakage_detected"] is True
        assert decision["unauthorized_orders_count"] == 1
        assert decision["unauthorized_positions_opened_count"] == 1
        assert "pc_legacy" in report["leakage_summary"]["affected_cycles"]
        assert report["leakage_summary"]["source_path_counts"]["legacy_score_meta"] >= 1


def test_blocked_attempt_is_not_counted_as_leakage() -> None:
    settings = PaperOrderLeakageGuardSettings(max_event_lines=1000)
    blocked = build_legacy_paper_order_blocked_event(
        settings=settings,
        cycle_id="pc_guarded",
        symbol="ETH/USDT",
        side="SELL",
        combination="ScoreOnly+Meta_OK(p:70%,q:72%)",
        source_path="legacy_score_meta",
    )
    summary = summarize_order_leakage_events([blocked], settings=settings)
    assert summary["legacy_order_leakage_detected"] is False
    assert summary["unauthorized_orders_count"] == 0
    assert summary["unauthorized_positions_opened_count"] == 0
    assert summary["blocked_legacy_order_attempts"] == 1


if __name__ == "__main__":
    test_guard_blocks_default_legacy_order_attempt()
    test_leakage_report_detects_historical_unauthorized_order_and_position()
    test_blocked_attempt_is_not_counted_as_leakage()
    print("Paper order leakage guard tests passed.")
