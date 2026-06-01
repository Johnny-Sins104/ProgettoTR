from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd

from trading_bot.core.lsr_v2_runtime_bridge import (
    READY_DECISION,
    RUNTIME_BRIDGE_EVENT_TYPE,
    RUNTIME_CANDIDATE_EVENT_TYPE,
    LSRV2RuntimeBridgeSettings,
    build_lsr_v2_runtime_bridge_events_for_symbol,
    write_lsr_v2_runtime_bridge_artifacts,
)
from trading_bot.core.lsr_v2_paper_supervised_bridge import CONFIRMATION_PHRASE, LSRV2PaperSupervisedBridgeSettings
from trading_bot.core.paper_once_runner_footer import load_lsr_v2_runtime_bridge_footer_summary, print_runner_once_footer_from_events


def _promotion_pass() -> dict:
    return {
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
    }


def _candidate_df() -> pd.DataFrame:
    rows: list[dict] = []
    for _ in range(20):
        rows.append({"Open": 102.0, "High": 105.0, "Low": 100.0, "Close": 102.0, "Volume": 100.0})
    rows.append({"Open": 101.0, "High": 102.0, "Low": 99.50, "Close": 100.40, "Volume": 140.0})
    rows.append({"Open": 100.4, "High": 106.0, "Low": 100.2, "Close": 105.50, "Volume": 130.0})
    rows.append({"Open": 105.5, "High": 106.2, "Low": 100.05, "Close": 104.00, "Volume": 120.0})
    for _ in range(8):
        rows.append({"Open": 102.0, "High": 105.0, "Low": 100.0, "Close": 102.0, "Volume": 100.0})
    return pd.DataFrame(rows, index=pd.date_range("2026-05-28", periods=len(rows), freq="5min"))


def _flat_df() -> pd.DataFrame:
    rows = [{"Open": 102.0, "High": 105.0, "Low": 100.0, "Close": 102.0, "Volume": 100.0} for _ in range(40)]
    return pd.DataFrame(rows, index=pd.date_range("2026-05-28", periods=len(rows), freq="5min"))


def test_builds_cycle_scoped_candidate_and_bridge_events_fail_closed() -> None:
    bridge_settings = LSRV2PaperSupervisedBridgeSettings(operator_enable=True, operator_confirmation=CONFIRMATION_PHRASE)
    candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
        df=_candidate_df(),
        cycle_id="pc_cycle_1",
        symbol="BTC/USDT",
        timeframe="5m",
        promotion_gate_report=_promotion_pass(),
        bridge_settings=bridge_settings,
        runtime_settings=LSRV2RuntimeBridgeSettings(max_recent_candidate_bars=6),
    )

    assert candidate_event["event_type"] == RUNTIME_CANDIDATE_EVENT_TYPE
    assert candidate_event["cycle_id"] == "pc_cycle_1"
    assert candidate_event["symbol"] == "BTC/USDT"
    assert candidate_event["candidate_ready"] is True
    assert bridge_event["event_type"] == RUNTIME_BRIDGE_EVENT_TYPE
    assert bridge_event["cycle_id"] == "pc_cycle_1"
    assert bridge_event["would_route"] is True
    assert bridge_event["would_submit"] is False
    assert bridge_event["broker_submit_called"] is False
    assert bridge_event["orders_submitted_by_lsr_v2_runtime_bridge"] == 0
    assert bridge_event["positions_opened_by_lsr_v2_runtime_bridge"] == 0


def test_no_runtime_candidate_still_emits_symbol_scoped_audit() -> None:
    candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
        df=_flat_df(),
        cycle_id="pc_no_candidate",
        symbol="ETH/USDT",
        timeframe="5m",
        promotion_gate_report=_promotion_pass(),
        runtime_settings=LSRV2RuntimeBridgeSettings(max_recent_candidate_bars=6),
    )

    assert candidate_event["event_type"] == RUNTIME_CANDIDATE_EVENT_TYPE
    assert candidate_event["candidate_ready"] is False
    assert candidate_event["detected_candidates"] == 0
    assert bridge_event["would_route"] is False
    assert bridge_event["would_submit"] is False
    assert "no_lsr_v2_runtime_candidate_ready" in bridge_event["blocked_reasons"]


def test_runtime_artifacts_are_cycle_scoped_and_detect_stale_standalone_report(tmp_path: Path) -> None:
    candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
        df=_candidate_df(),
        cycle_id="pc_new",
        symbol="BTC/USDT",
        timeframe="5m",
        promotion_gate_report=_promotion_pass(),
        runtime_settings=LSRV2RuntimeBridgeSettings(data_dir=str(tmp_path), max_recent_candidate_bars=6),
    )
    report = write_lsr_v2_runtime_bridge_artifacts(
        data_dir=tmp_path,
        cycle_id="pc_new",
        events=[candidate_event, bridge_event],
        settings=LSRV2RuntimeBridgeSettings(data_dir=str(tmp_path)),
        standalone_report={"latest_cycle_id": "pc_old", "bridge_events": 12, "candidate_ready_events": 12},
        promotion_gate_report=_promotion_pass(),
    )

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["runtime_bridge_events"] == 1
    assert report["runtime_candidate_ready_events"] == 1
    assert report["standalone_bridge_events"] == 12
    assert report["lsr_v2_bridge_report_cycle_id"] == "pc_old"
    assert report["lsr_v2_bridge_report_stale"] is True
    assert report["runtime_would_submit_count"] == 0
    assert (tmp_path / "lsr_v2_runtime_bridge_report.json").exists()
    assert (tmp_path / "lsr_v2_runtime_bridge_audit.jsonl").exists()


def test_runtime_footer_summary_is_fail_closed_when_report_is_hostile(tmp_path: Path) -> None:
    (tmp_path / "lsr_v2_runtime_bridge_report.json").write_text(json.dumps({
        "decision": READY_DECISION,
        "runtime_bridge_events": 4,
        "runtime_candidate_ready_events": 1,
        "runtime_would_submit_count": 99,
        "orders_submitted_by_lsr_v2_runtime_bridge": 3,
        "positions_opened_by_lsr_v2_runtime_bridge": 2,
        "broker_submit_called": True,
        "execution_enabled": True,
        "routing_enabled": True,
        "paper_order_submission_enabled": True,
        "promotion_ready": True,
    }), encoding="utf-8")

    summary = load_lsr_v2_runtime_bridge_footer_summary(tmp_path)

    assert summary["runtime_would_submit_count"] == 0
    assert summary["orders_submitted_by_lsr_v2_runtime_bridge"] == 0
    assert summary["positions_opened_by_lsr_v2_runtime_bridge"] == 0
    assert summary["broker_submit_called"] is False
    assert summary["execution_enabled"] is False
    assert summary["routing_enabled"] is False
    assert summary["paper_order_submission_enabled"] is False
    assert summary["promotion_ready"] is False


def test_runner_footer_prints_runtime_cycle_scoped_lsr_v2_lines(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": "2026-05-28T10:00:00+00:00",
            "event_type": "CYCLE_COMPLETED",
            "cycle_id": "pc_footer_runtime",
            "scanned": 4,
            "signals": 0,
            "orders": 0,
            "open_positions": 0,
        }) + "\n")
    (tmp_path / "lsr_v2_runtime_bridge_report.json").write_text(json.dumps({
        "decision": READY_DECISION,
        "cycle_id": "pc_footer_runtime",
        "runtime_bridge_events": 4,
        "runtime_candidate_events": 4,
        "runtime_candidate_ready_events": 1,
        "runtime_would_route_count": 0,
        "runtime_would_submit_count": 0,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "standalone_bridge_events": 12,
        "lsr_v2_bridge_report_cycle_id": "pc_old",
        "lsr_v2_bridge_report_stale": True,
    }), encoding="utf-8")

    stream = StringIO()
    printed = print_runner_once_footer_from_events(events_path, stream=stream, force=True)
    output = stream.getvalue()

    assert printed is True
    assert "prompt=29.4.4s-10f-1" in output
    assert "lsr_v2_runtime_bridge_decision=LSR_V2_RUNTIME_CYCLE_BRIDGE_READY_DIAGNOSTIC" in output
    assert "lsr_v2_runtime_cycle_id=pc_footer_runtime" in output
    assert "lsr_v2_runtime_bridge_events=4" in output
    assert "lsr_v2_runtime_candidate_ready_events=1" in output
    assert "lsr_v2_runtime_would_submit_count=0" in output
    assert "orders_submitted_by_lsr_v2_runtime_bridge=0" in output
    assert "positions_opened_by_lsr_v2_runtime_bridge=0" in output
    assert "lsr_v2_bridge_report_stale=true" in output


def test_s10f_operator_alias_env_enables_would_route(monkeypatch) -> None:
    monkeypatch.setenv("LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION", "I_UNDERSTAND_PAPER_ONLY")
    bridge_settings = LSRV2PaperSupervisedBridgeSettings.from_config()
    assert bridge_settings.operator_enable is True
    assert bridge_settings.operator_confirmation_ok is True

    candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
        df=_candidate_df(),
        cycle_id="pc_operator_route",
        symbol="BTC/USDT",
        timeframe="5m",
        promotion_gate_report=_promotion_pass(),
        bridge_settings=bridge_settings,
        runtime_settings=LSRV2RuntimeBridgeSettings(max_recent_candidate_bars=6),
    )

    assert candidate_event["candidate_ready"] is True
    assert bridge_event["would_route"] is True
    assert bridge_event["blocked_reason"] == "paper_supervised_bridge_fail_closed"
    assert bridge_event["would_submit"] is False
    assert bridge_event["broker_submit_called"] is False
    assert bridge_event["orders_submitted_by_lsr_v2_runtime_bridge"] == 0
    assert bridge_event["positions_opened_by_lsr_v2_runtime_bridge"] == 0


def test_s10f_operator_route_artifacts_are_submit_blocked(tmp_path: Path) -> None:
    from trading_bot.core.lsr_v2_runtime_bridge import (
        OPERATOR_ROUTE_READY_DECISION,
        summarize_lsr_v2_operator_route_audit,
        write_lsr_v2_operator_route_audit_artifacts,
    )

    bridge_settings = LSRV2PaperSupervisedBridgeSettings(operator_enable=True, operator_confirmation="I_UNDERSTAND_PAPER_ONLY")
    candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
        df=_candidate_df(),
        cycle_id="pc_operator_artifact",
        symbol="BTC/USDT",
        timeframe="5m",
        promotion_gate_report=_promotion_pass(),
        bridge_settings=bridge_settings,
        runtime_settings=LSRV2RuntimeBridgeSettings(max_recent_candidate_bars=6, data_dir=str(tmp_path)),
    )
    report = summarize_lsr_v2_operator_route_audit(
        cycle_id="pc_operator_artifact",
        events=[candidate_event, bridge_event],
        data_dir=tmp_path,
        settings=LSRV2RuntimeBridgeSettings(data_dir=str(tmp_path)),
    )
    assert report["decision"] == OPERATOR_ROUTE_READY_DECISION
    assert report["would_route_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_operator_route_audit"] == 0
    assert report["positions_opened_by_lsr_v2_operator_route_audit"] == 0

    written = write_lsr_v2_operator_route_audit_artifacts(
        data_dir=tmp_path,
        cycle_id="pc_operator_artifact",
        events=[candidate_event, bridge_event],
        settings=LSRV2RuntimeBridgeSettings(data_dir=str(tmp_path)),
    )
    assert written["decision"] == OPERATOR_ROUTE_READY_DECISION
    assert (tmp_path / "lsr_v2_operator_route_audit_report.json").exists()
    assert (tmp_path / "lsr_v2_operator_route_audit.jsonl").exists()


def test_s10f1_operator_route_runner_uses_paper_events_strict_cycle_scope(tmp_path: Path, capsys) -> None:
    from trading_bot.run_lsr_v2_operator_route_audit import main

    events_path = tmp_path / "paper_events.jsonl"
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event_type": RUNTIME_CANDIDATE_EVENT_TYPE, "cycle_id": "pc_old", "candidate_ready": True}) + "\n")
        fh.write(json.dumps({"event_type": RUNTIME_BRIDGE_EVENT_TYPE, "cycle_id": "pc_old", "runtime_cycle_scoped": True, "would_route": True}) + "\n")
        for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]:
            ready = symbol == "BTC/USDT"
            fh.write(json.dumps({"event_type": RUNTIME_CANDIDATE_EVENT_TYPE, "cycle_id": "pc_current", "symbol": symbol, "candidate_ready": ready}) + "\n")
            fh.write(json.dumps({
                "event_type": RUNTIME_BRIDGE_EVENT_TYPE,
                "cycle_id": "pc_current",
                "symbol": symbol,
                "runtime_cycle_scoped": True,
                "operator_enable": True,
                "operator_confirmation_ok": True,
                "operator_authorized": True,
                "would_route": ready,
                "would_submit": False,
                "orders_submitted_by_lsr_v2_runtime_bridge": 0,
                "positions_opened_by_lsr_v2_runtime_bridge": 0,
            }) + "\n")
        fh.write(json.dumps({"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_current"}) + "\n")

    # Runtime mirror contains duplicated current-cycle rows and must not inflate counts.
    runtime_path = tmp_path / "lsr_v2_runtime_bridge_audit.jsonl"
    current_rows = [line for line in events_path.read_text(encoding="utf-8").splitlines() if "pc_current" in line and "CYCLE_COMPLETED" not in line]
    runtime_path.write_text("\n".join(current_rows + current_rows) + "\n", encoding="utf-8")
    (tmp_path / "lsr_v2_runtime_bridge_report.json").write_text(json.dumps({"cycle_id": "pc_current"}), encoding="utf-8")

    assert main(["--data-dir", str(tmp_path)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    report = json.loads((tmp_path / "lsr_v2_operator_route_audit_report.json").read_text(encoding="utf-8"))

    assert stdout["cycle_id"] == "pc_current"
    assert stdout["event_source"] == "paper_events_jsonl"
    assert stdout["strict_cycle_scope"] is True
    assert report["runtime_candidate_events"] == 4
    assert report["runtime_candidate_ready_events"] == 1
    assert report["runtime_bridge_events"] == 4
    assert report["would_route_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["historical_lsr_v2_events"] == 2
    assert report["orders_submitted_by_lsr_v2_operator_route_audit"] == 0
    assert report["positions_opened_by_lsr_v2_operator_route_audit"] == 0


def test_s10f1_operator_route_runner_dedupes_runtime_jsonl_fallback(tmp_path: Path) -> None:
    from trading_bot.run_lsr_v2_operator_route_audit import main

    rows = []
    for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]:
        ready = symbol == "BTC/USDT"
        rows.append({"event_type": RUNTIME_CANDIDATE_EVENT_TYPE, "cycle_id": "pc_fallback", "symbol": symbol, "candidate_ready": ready})
        rows.append({
            "event_type": RUNTIME_BRIDGE_EVENT_TYPE,
            "cycle_id": "pc_fallback",
            "symbol": symbol,
            "runtime_cycle_scoped": True,
            "operator_enable": True,
            "operator_confirmation_ok": True,
            "operator_authorized": True,
            "would_route": ready,
            "would_submit": False,
        })
    with (tmp_path / "lsr_v2_runtime_bridge_audit.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows + rows + rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    (tmp_path / "lsr_v2_runtime_bridge_report.json").write_text(json.dumps({"cycle_id": "pc_fallback"}), encoding="utf-8")

    assert main(["--data-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "lsr_v2_operator_route_audit_report.json").read_text(encoding="utf-8"))

    assert report["event_source"] == "runtime_bridge_jsonl_fallback"
    assert report["runtime_jsonl_deduplicated"] is True
    assert report["runtime_candidate_events"] == 4
    assert report["runtime_candidate_ready_events"] == 1
    assert report["runtime_bridge_events"] == 4
    assert report["would_route_count"] == 1
    assert report["would_submit_count"] == 0
