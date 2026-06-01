from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_cost_drawdown_attribution import (
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2CostDrawdownAttributionSettings,
    run_lsr_v2_cost_drawdown_attribution,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_robustness(path: Path, blockers: list[str] | None = None) -> None:
    path.write_text(json.dumps({
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_FAILED" if blockers else "LSR_V2_READY_FOR_PROMOTION_GATE",
        "blockers": blockers or [],
        "promotion_ready": False,
    }, sort_keys=True), encoding="utf-8")


def _trade(i: int, *, cost_model: str, net_r: float, symbol: str = "BTC/USDT", timeframe: str = "5m", side: str = "BUY") -> dict:
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
        "window_size": 50000,
        "window_label": "50k",
        "cost_model": cost_model,
        "entry_index": i * 10,
        "exit_index": i * 10 + 5,
        "entry_timestamp": f"2026-01-01T{(i // 60):02d}:{(i % 60):02d}:00Z",
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


def _rows(count: int, *, primary_net: float = 0.30, severe_net: float = 0.16, drawdown_cluster: bool = False, cost_fail: bool = False) -> list[dict]:
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    tfs = ["5m", "15m"]
    sides = ["BUY", "SELL"]
    rows: list[dict] = []
    for i in range(count):
        p = primary_net
        if drawdown_cluster and 30 <= i < 42:
            p = -1.4
        elif drawdown_cluster and i >= 42:
            p = 0.45
        s = severe_net if not cost_fail else -0.05
        if drawdown_cluster and 30 <= i < 42:
            s = p - 0.30
        symbol = symbols[i % len(symbols)]
        timeframe = tfs[(i // len(symbols)) % len(tfs)]
        side = sides[i % len(sides)]
        rows.append(_trade(i, cost_model="conservative", net_r=p, symbol=symbol, timeframe=timeframe, side=side))
        rows.append(_trade(i, cost_model="severe", net_r=s, symbol=symbol, timeframe=timeframe, side=side))
    return rows


def test_no_trade_rows_returns_safe_warn(tmp_path: Path):
    report = run_lsr_v2_cost_drawdown_attribution(LSRV2CostDrawdownAttributionSettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_NO_TRADES"
    assert report["orders_submitted_by_lsr_v2_cost_drawdown_attribution"] == 0
    assert report["positions_opened_by_lsr_v2_cost_drawdown_attribution"] == 0
    assert Path(report["report"]).exists()
    assert Path(report["drawdown_segments_jsonl"]).exists()


def test_balanced_profile_is_attribution_ready_without_promotion(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _rows(80, primary_net=0.30, severe_net=0.20))
    _write_robustness(tmp_path / "lsr_v2_robustness_validation_report.json")
    report = run_lsr_v2_cost_drawdown_attribution(
        LSRV2CostDrawdownAttributionSettings(data_dir=str(tmp_path), max_drawdown_r=25.0)
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_COST_DRAWDOWN_ATTRIBUTION_READY"
    assert report["primary_trade_count"] == 80
    assert report["severe_trade_count"] == 80
    assert report["cost_degradation_non_destructive"] is True
    assert report["promotion_ready"] is False
    assert Path(report["cost_degradation_report"]).exists()
    assert Path(report["drawdown_attribution_report"]).exists()
    assert Path(report["risk_overlay_preflight_report"]).exists()


def test_cost_degradation_confirmed_is_classified(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _rows(80, primary_net=0.30, severe_net=-0.10, cost_fail=True))
    _write_robustness(tmp_path / "lsr_v2_robustness_validation_report.json", ["cost_degradation_failed"])
    report = run_lsr_v2_cost_drawdown_attribution(LSRV2CostDrawdownAttributionSettings(data_dir=str(tmp_path)))
    assert report["status"] == "PASS"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_CONFIRMED"
    assert "COST_DEGRADATION_CONFIRMED" in report["classification_labels"]
    assert report["cost_degradation_non_destructive"] is False
    cost = json.loads(Path(report["cost_degradation_report"]).read_text(encoding="utf-8"))
    assert cost["paired_trade_count"] == 80
    assert cost["severe_positive_ratio"] == 0.0


def test_drawdown_cluster_and_overlay_are_reported(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _rows(90, primary_net=0.20, severe_net=0.12, drawdown_cluster=True))
    _write_robustness(tmp_path / "lsr_v2_robustness_validation_report.json", ["max_drawdown_above_limit"])
    report = run_lsr_v2_cost_drawdown_attribution(
        LSRV2CostDrawdownAttributionSettings(data_dir=str(tmp_path), max_drawdown_r=5.0, min_segment_depth_r=1.0, max_drawdown_segment_share=0.20)
    )
    assert report["status"] == "PASS"
    assert report["decision"] in {
        "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_REQUIRED",
        "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_CLUSTERED",
        "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_CONFIRMED",
    }
    assert report["max_drawdown_above_limit"] is True
    assert report["written_drawdown_segments"] > 0
    lines = Path(report["drawdown_segments_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert lines
    first = json.loads(lines[0])
    assert first["event_type"] == "LSR_V2_DRAWDOWN_SEGMENT"
    assert first["orders_submitted_by_lsr_v2_drawdown_attribution"] == 0


def test_duplicate_window_representations_are_deduped(tmp_path: Path):
    rows = []
    for row in _rows(60, primary_net=0.25, severe_net=0.16):
        rows.append(row)
        dup = dict(row)
        dup["window_size"] = 150000
        dup["window_label"] = "150k"
        rows.append(dup)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", rows)
    report = run_lsr_v2_cost_drawdown_attribution(LSRV2CostDrawdownAttributionSettings(data_dir=str(tmp_path)))
    assert report["raw_trade_rows"] == 240
    assert report["primary_trade_count"] == 60
    assert report["severe_trade_count"] == 60
