from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.equity_forensics import EquityForensicsSettings, build_equity_curve, write_equity_forensics_report


def _rows():
    return [
        {
            "row_type": "closed_trade",
            "position_id": "p1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "archetype": "LSR",
            "closed_at": "2026-05-28T12:00:00+00:00",
            "net_pnl": 10.0,
            "r_multiple": 1.0,
        },
        {
            "row_type": "closed_trade",
            "position_id": "p2",
            "symbol": "BTC/USDT",
            "side": "SELL",
            "archetype": "LSR",
            "closed_at": "2026-05-28T13:00:00+00:00",
            "net_pnl": -5.0,
            "r_multiple": -0.5,
        },
    ]


def test_build_equity_curve_tracks_drawdown():
    curve = build_equity_curve(_rows(), starting_equity=100.0)
    assert len(curve) == 2
    assert curve[0]["equity"] == 110.0
    assert curve[1]["equity"] == 105.0
    assert curve[1]["drawdown"] == 5.0
    assert round(curve[1]["drawdown_pct"], 6) == round(5.0 / 110.0 * 100.0, 6)


def test_write_equity_forensics_report_reads_trade_jsonl(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with (data_dir / "trade_level_telemetry.jsonl").open("w", encoding="utf-8") as fh:
        for row in _rows():
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    report = write_equity_forensics_report(EquityForensicsSettings(data_dir=str(data_dir), starting_equity=100.0))
    assert report["decision"] == "EQUITY_FORENSICS_READY_DIAGNOSTIC"
    assert report["closed_trades"] == 2
    assert report["final_equity"] == 105.0
    assert report["max_drawdown"] == 5.0
    assert report["promotion_ready"] is False
    assert report["orders_submitted_by_equity_forensics"] == 0
    assert (data_dir / "equity_forensics_report.json").exists()
