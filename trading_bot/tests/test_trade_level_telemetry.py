from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.trade_level_telemetry import TradeTelemetrySettings, build_trade_rows_from_events, export_trade_level_telemetry


def _sample_events():
    return [
        {
            "ts": "2026-05-28T12:00:00+00:00",
            "event_type": "SIGNAL_DETECTED",
            "cycle_id": "pc_1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "regime": "RANGING",
            "scenario": "LOW_VOL_RANGE",
            "confidence": {"setup_archetype": "LIQUIDITY_SWEEP_REVERSAL", "regime": "RANGING"},
        },
        {
            "ts": "2026-05-28T12:01:00+00:00",
            "event_type": "PAPER_ORDER_SUBMITTED",
            "cycle_id": "pc_1",
            "order_id": "po_1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order": {
                "order_id": "po_1",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "qty": 0.1,
                "filled_price": 100.0,
                "requested_price": 100.0,
                "metadata": {
                    "cycle_id": "pc_1",
                    "setup_archetype": "LIQUIDITY_SWEEP_REVERSAL",
                    "regime": "RANGING",
                    "crypto_scenario": "LOW_VOL_RANGE",
                },
            },
        },
        {
            "ts": "2026-05-28T12:01:00+00:00",
            "event_type": "POSITION_OPENED",
            "cycle_id": "pc_1",
            "order_id": "po_1",
            "position_id": "pp_1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "position": {
                "position_id": "pp_1",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "qty": 0.1,
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "opened_at": "2026-05-28T12:01:00+00:00",
                "fees_paid": 0.004,
                "metadata": {
                    "cycle_id": "pc_1",
                    "source_order_id": "po_1",
                    "setup_archetype": "LIQUIDITY_SWEEP_REVERSAL",
                    "regime": "RANGING",
                    "crypto_scenario": "LOW_VOL_RANGE",
                },
            },
        },
        {
            "ts": "2026-05-28T12:31:00+00:00",
            "event_type": "POSITION_CLOSED",
            "position_id": "pp_1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "reason": "TP",
            "position": {
                "position_id": "pp_1",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "qty": 0.1,
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "opened_at": "2026-05-28T12:01:00+00:00",
                "closed_at": "2026-05-28T12:31:00+00:00",
                "exit_price": 110.0,
                "close_reason": "TP",
                "realized_pnl": 0.9912,
                "fees_paid": 0.0088,
                "metadata": {
                    "cycle_id": "pc_1",
                    "source_order_id": "po_1",
                    "setup_archetype": "LIQUIDITY_SWEEP_REVERSAL",
                    "regime": "RANGING",
                    "crypto_scenario": "LOW_VOL_RANGE",
                },
            },
        },
    ]


def test_build_trade_rows_from_position_events():
    rows = build_trade_rows_from_events(_sample_events(), TradeTelemetrySettings())
    assert len(rows) == 1
    row = rows[0]
    assert row["row_type"] == "closed_trade"
    assert row["symbol"] == "BTC/USDT"
    assert row["archetype"] == "LIQUIDITY_SWEEP_REVERSAL"
    assert row["regime"] == "RANGING"
    assert row["exit_reason"] == "TP"
    assert row["net_pnl"] == 0.9912
    assert row["r_multiple"] == 1.9824
    assert row["mae_r"] is None
    assert row["mae_mfe_status"] == "UNAVAILABLE_WITHOUT_INTRATRADE_BAR_PATH"
    assert row["orders_submitted_by_telemetry"] == 0
    assert row["positions_opened_by_telemetry"] == 0


def test_export_trade_level_telemetry_writes_jsonl_and_report(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with (data_dir / "paper_events.jsonl").open("w", encoding="utf-8") as fh:
        for event in _sample_events():
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    report = export_trade_level_telemetry(TradeTelemetrySettings(data_dir=str(data_dir)))

    assert report["status"] == "PASS"
    assert report["decision"] == "TRADE_LEVEL_TELEMETRY_READY_DIAGNOSTIC"
    assert report["closed_trades"] == 1
    assert report["trade_level_rows"] == 1
    assert report["summary"]["avg_r"] == 1.9824
    assert report["promotion_ready"] is False
    assert (data_dir / "trade_level_telemetry.jsonl").exists()
    assert (data_dir / "trade_level_summary_report.json").exists()


def test_export_handles_missing_event_log_without_state_mutation(tmp_path: Path):
    data_dir = tmp_path / "data"
    report = export_trade_level_telemetry(TradeTelemetrySettings(data_dir=str(data_dir)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_NO_EVENT_LOG"
    assert report["orders_submitted_by_telemetry"] == 0
    assert report["positions_opened_by_telemetry"] == 0
    assert (data_dir / "trade_level_telemetry.jsonl").exists()
