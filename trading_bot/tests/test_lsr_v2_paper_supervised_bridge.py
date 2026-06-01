from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_supervised_bridge import (
    CONFIRMATION_PHRASE,
    EVENT_TYPE,
    NO_CANDIDATES_DECISION,
    PROMOTION_MISSING_DECISION,
    READY_DECISION,
    LSRV2PaperSupervisedBridgeSettings,
    build_lsr_v2_paper_supervised_bridge_event,
    write_lsr_v2_paper_supervised_bridge_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for payload in payloads:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _promotion_pass(data_dir: Path) -> None:
    _write_json(
        data_dir / "lsr_v2_promotion_gate_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_PAPER_SUPERVISED_CANDIDATE",
            "paper_supervised_candidate": True,
            "paper_supervised_readiness_preflight_pass": True,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_called": False,
        },
    )


def _candidate(side: str = "BUY") -> dict:
    return {
        "event_type": "LSR_V2_CANDIDATE_AUDIT",
        "candidate_id": f"cand_{side.lower()}",
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "side": side,
        "archetype": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "candidate_ready": True,
        "quality": {"grade": "A"},
        "levels": {"entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0},
    }


def test_build_event_is_fail_closed_even_when_operator_authorized() -> None:
    settings = LSRV2PaperSupervisedBridgeSettings(
        operator_enable=True,
        operator_confirmation=CONFIRMATION_PHRASE,
    )
    event = build_lsr_v2_paper_supervised_bridge_event(
        settings=settings,
        promotion_gate_report={
            "status": "PASS",
            "decision": "LSR_V2_PAPER_SUPERVISED_CANDIDATE",
            "paper_supervised_candidate": True,
            "paper_supervised_readiness_preflight_pass": True,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_called": False,
        },
        candidate_event=_candidate(),
    )
    assert event["event_type"] == EVENT_TYPE
    assert event["would_route"] is True
    assert event["would_submit"] is False
    assert event["blocked_reason"] == "paper_supervised_bridge_fail_closed"
    assert event["orders_submitted_by_lsr_v2_bridge"] == 0
    assert event["positions_opened_by_lsr_v2_bridge"] == 0


def test_operator_disabled_blocks_route_but_remains_safe() -> None:
    event = build_lsr_v2_paper_supervised_bridge_event(
        settings=LSRV2PaperSupervisedBridgeSettings(),
        promotion_gate_report={
            "status": "PASS",
            "decision": "LSR_V2_PAPER_SUPERVISED_CANDIDATE",
            "paper_supervised_candidate": True,
            "paper_supervised_readiness_preflight_pass": True,
        },
        candidate_event=_candidate("SELL"),
    )
    assert event["would_route"] is False
    assert event["would_submit"] is False
    assert "operator_disabled" in event["blocked_reasons"]
    assert event["broker_submit_called"] is False


def test_report_missing_promotion_gate_is_warn(tmp_path: Path) -> None:
    report = write_lsr_v2_paper_supervised_bridge_report(tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == PROMOTION_MISSING_DECISION
    assert report["orders_submitted_by_lsr_v2_bridge"] == 0
    assert report["positions_opened_by_lsr_v2_bridge"] == 0


def test_report_no_candidates_is_warn(tmp_path: Path) -> None:
    _promotion_pass(tmp_path)
    report = write_lsr_v2_paper_supervised_bridge_report(tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == NO_CANDIDATES_DECISION
    assert report["promotion_gate_pass"] is True
    assert report["candidate_ready_events"] == 0


def test_report_ready_with_candidates_default_operator_fail_closed(tmp_path: Path) -> None:
    _promotion_pass(tmp_path)
    _append_jsonl(tmp_path / "lsr_v2_candidate_audit.jsonl", [_candidate(), {**_candidate("SELL"), "candidate_id": "cand_sell"}])
    report = write_lsr_v2_paper_supervised_bridge_report(tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["candidate_ready_events"] == 2
    assert report["bridge_events"] == 2
    assert report["would_route_count"] == 0
    assert report["would_submit_count"] == 0
    assert report["execution_enabled"] is False
    assert report["routing_enabled"] is False
    assert Path(report["bridge_jsonl"]).exists()
