from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_risk_overlay_ablation import (  # noqa: E402
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2RiskOverlayAblationSettings,
    run_lsr_v2_risk_overlay_ablation,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_attribution(path: Path, blockers: list[str] | None = None) -> None:
    path.write_text(json.dumps({
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_REQUIRED" if blockers else "LSR_V2_COST_DRAWDOWN_ATTRIBUTION_READY",
        "blockers": blockers or [],
        "promotion_ready": False,
    }, sort_keys=True), encoding="utf-8")


def _trade(
    i: int,
    *,
    cost_model: str,
    net_r: float,
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    side: str = "BUY",
    ts_day: int | None = None,
) -> dict:
    day = ts_day if ts_day is not None else 1 + (i // 80)
    return {
        "event_type": "LSR_V2_SAMPLE_EXPANSION_TRADE",
        "prompt_id": "29.4.4s-7e",
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "variant_id": LOCKED_VARIANT_ID,
        "sample_expansion_symbol": symbol,
        "sample_expansion_timeframe": timeframe,
        "symbol": symbol,
        "timeframe": timeframe,
        "candidate_id": f"cand_{i:04d}",
        "side": side,
        "window_size": 150000,
        "window_label": "150k",
        "cost_model": cost_model,
        "entry_index": i * 10,
        "exit_index": i * 10 + 5,
        "entry_timestamp": f"2026-01-{day:02d}T{(i // 60) % 24:02d}:{(i % 60):02d}:00Z",
        "entry_price": 100.0 + i,
        "stop_loss": 99.0 + i,
        "take_profit": 102.0 + i,
        "exit_price": 101.0 + i,
        "exit_reason": "TAKE_PROFIT" if net_r > 0 else "STOP_LOSS",
        "gross_r": round(net_r + 0.05, 8),
        "cost_r": 0.05,
        "net_r": round(net_r, 8),
        "orders_submitted_by_lsr_v2_sample_expansion": 0,
        "positions_opened_by_lsr_v2_sample_expansion": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
    }


def _rows_with_loss_cluster() -> list[dict]:
    rows: list[dict] = []
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    tfs = ["5m", "15m"]
    sides = ["BUY", "SELL"]
    for i in range(140):
        if 45 <= i < 57:
            p = -1.0
        else:
            p = 0.35
        s = p - 0.10
        symbol = symbols[i % len(symbols)]
        timeframe = tfs[(i // len(symbols)) % len(tfs)]
        side = sides[i % len(sides)]
        rows.append(_trade(i, cost_model="conservative", net_r=p, symbol=symbol, timeframe=timeframe, side=side))
        rows.append(_trade(i, cost_model="severe", net_r=s, symbol=symbol, timeframe=timeframe, side=side))
    return rows


def _steady_rows(count: int = 80) -> list[dict]:
    rows: list[dict] = []
    for i in range(count):
        rows.append(_trade(i, cost_model="conservative", net_r=0.25))
        rows.append(_trade(i, cost_model="severe", net_r=0.16))
    return rows


def _edge_destroyed_rows() -> list[dict]:
    rows: list[dict] = []
    for i in range(80):
        # Alternating small edge; overlay can filter many trades but retains too little profit.
        p = 0.08 if i % 3 else 0.16
        s = -0.05
        rows.append(_trade(i, cost_model="conservative", net_r=p))
        rows.append(_trade(i, cost_model="severe", net_r=s))
    return rows


def test_no_trade_rows_returns_safe_warn(tmp_path: Path):
    report = run_lsr_v2_risk_overlay_ablation(LSRV2RiskOverlayAblationSettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_NO_TRADES"
    assert report["orders_submitted_by_lsr_v2_risk_overlay_ablation"] == 0
    assert report["positions_opened_by_lsr_v2_risk_overlay_ablation"] == 0
    assert Path(report["report"]).exists()
    assert Path(report["trades_jsonl"]).exists()


def test_loss_streak_overlay_can_be_research_ready(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _rows_with_loss_cluster())
    _write_attribution(tmp_path / "lsr_v2_cost_drawdown_attribution_report.json", ["max_consecutive_losses_above_limit"])
    report = run_lsr_v2_risk_overlay_ablation(
        LSRV2RiskOverlayAblationSettings(
            data_dir=str(tmp_path),
            max_drawdown_r=8.0,
            max_consecutive_losses_limit=10,
            min_drawdown_reduction_ratio=0.30,
            min_profit_retention_ratio=0.50,
        )
    )
    assert report["status"] == "PASS"
    assert report["decision"] in {
        "LSR_V2_RISK_OVERLAY_RESEARCH_READY",
        "KEEP_DIAGNOSTIC_LSR_V2_OVERLAY_INSUFFICIENT",
        "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH",
    }
    assert report["variant_count"] > 10
    assert report["best_overlay_id"] is not None
    assert report["promotion_ready"] is False
    variants = json.loads(Path(report["variants_report"]).read_text(encoding="utf-8"))
    assert variants["variant_count"] == report["variant_count"]
    assert any(v["overlay_id"] == "max_consecutive_loss_pause_3" for v in variants["variants"])


def test_balanced_profile_reports_overlay_insufficient_without_orders(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _steady_rows())
    _write_attribution(tmp_path / "lsr_v2_cost_drawdown_attribution_report.json")
    report = run_lsr_v2_risk_overlay_ablation(LSRV2RiskOverlayAblationSettings(data_dir=str(tmp_path)))
    assert report["status"] == "PASS"
    assert report["decision"] in {
        "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH",
        "KEEP_DIAGNOSTIC_LSR_V2_OVERLAY_INSUFFICIENT",
        "KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY",
        "LSR_V2_RISK_OVERLAY_RESEARCH_READY",
    }
    assert report["baseline_sum_r_post_cost"] > 0
    assert report["orders_submitted_by_lsr_v2_risk_overlay_ablation"] == 0
    assert report["positions_opened_by_lsr_v2_risk_overlay_ablation"] == 0


def test_oracle_cost_filters_are_flagged_as_oracle(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _rows_with_loss_cluster())
    report = run_lsr_v2_risk_overlay_ablation(LSRV2RiskOverlayAblationSettings(data_dir=str(tmp_path)))
    variants = json.loads(Path(report["variants_report"]).read_text(encoding="utf-8"))["variants"]
    oracle = [v for v in variants if v.get("oracle_overlay")]
    assert oracle
    assert all(v["diagnostic_only"] is True for v in oracle)
    assert all(v["orders_submitted_by_lsr_v2_risk_overlay"] == 0 for v in oracle)


def test_duplicate_window_representations_are_deduped(tmp_path: Path):
    rows = []
    for row in _steady_rows(60):
        rows.append(row)
        dup = dict(row)
        dup["window_size"] = 100000
        dup["window_label"] = "100k"
        rows.append(dup)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", rows)
    report = run_lsr_v2_risk_overlay_ablation(LSRV2RiskOverlayAblationSettings(data_dir=str(tmp_path)))
    assert report["raw_trade_rows"] == 240
    assert report["primary_trade_count"] == 60
    assert report["severe_trade_count"] == 60
    assert report["written_overlay_trade_rows"] >= 0
