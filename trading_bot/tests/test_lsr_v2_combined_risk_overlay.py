from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_combined_risk_overlay import (  # noqa: E402
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    LSRV2CombinedRiskOverlaySettings,
    run_lsr_v2_combined_risk_overlay,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_risk_overlay_report(path: Path, blockers: list[str] | None = None) -> None:
    path.write_text(json.dumps({
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_OVERLAY_INSUFFICIENT" if blockers else "LSR_V2_RISK_OVERLAY_RESEARCH_READY",
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
        "candidate_id": f"cand_{i:05d}",
        "side": side,
        "window_size": 150000,
        "window_label": "150k",
        "cost_model": cost_model,
        "entry_index": i * 10,
        "exit_index": i * 10 + 5,
        "entry_timestamp": f"2026-01-{1 + (i // 80):02d}T{(i // 60) % 24:02d}:{(i % 60):02d}:00Z",
        "entry_price": 100.0 + i,
        "stop_loss": 99.0 + i,
        "take_profit": 102.0 + i,
        "exit_price": 101.0 + i,
        "exit_reason": "TAKE_PROFIT" if net_r > 0 else "STOP_LOSS",
        "gross_r": round(net_r + 0.05, 8),
        "cost_r": 0.05,
        "net_r": round(net_r, 8),
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
    }


def _cluster_rows() -> list[dict]:
    rows: list[dict] = []
    values: list[float] = []
    # Repeated profitable regions interrupted by long loss clusters; loss3 pause should remove the tail of each cluster.
    for _ in range(4):
        values.extend([0.45] * 35)
        values.extend([-1.0] * 8)
        values.extend([0.35] * 25)
    for i, value in enumerate(values):
        symbol = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"][i % 4]
        timeframe = ["5m", "15m"][(i // 4) % 2]
        side = ["BUY", "SELL"][i % 2]
        rows.append(_trade(i, cost_model="conservative", net_r=value, symbol=symbol, timeframe=timeframe, side=side))
        rows.append(_trade(i, cost_model="severe", net_r=value - 0.08, symbol=symbol, timeframe=timeframe, side=side))
    return rows


def _edge_destroyed_rows() -> list[dict]:
    rows: list[dict] = []
    for i in range(100):
        value = 0.12 if i % 4 else -0.35
        rows.append(_trade(i, cost_model="conservative", net_r=value))
        rows.append(_trade(i, cost_model="severe", net_r=value - 0.10))
    return rows


def test_no_trade_rows_returns_safe_warn(tmp_path: Path):
    report = run_lsr_v2_combined_risk_overlay(LSRV2CombinedRiskOverlaySettings(data_dir=str(tmp_path)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_NO_TRADES"
    assert report["orders_submitted_by_lsr_v2_combined_overlay"] == 0
    assert report["positions_opened_by_lsr_v2_combined_overlay"] == 0
    assert Path(report["report"]).exists()
    assert Path(report["trades_jsonl"]).exists()


def test_combined_overlay_can_pass_preflight_diagnostic(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _cluster_rows())
    _write_risk_overlay_report(tmp_path / "lsr_v2_risk_overlay_ablation_report.json", ["baseline_loss_streak_above_limit"])
    report = run_lsr_v2_combined_risk_overlay(
        LSRV2CombinedRiskOverlaySettings(
            data_dir=str(tmp_path),
            max_drawdown_r=8.0,
            max_consecutive_losses_limit=3,
            min_trades_kept=80,
            max_cost_degradation_ratio=1.25,
            min_severe_positive_ratio=0.50,
        )
    )
    assert report["status"] == "PASS"
    assert report["variant_count"] >= 10
    assert report["best_combined_overlay_id"] is not None
    assert report["best_combined_overlay_valid"] is True
    assert report["decision"] == "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS"
    assert report["promotion_ready"] is False
    assert report["orders_submitted_by_lsr_v2_combined_overlay"] == 0
    variants = json.loads(Path(report["variants_report"]).read_text(encoding="utf-8"))
    assert variants["valid_combined_overlay_count"] >= 1


def test_combined_overlay_insufficient_or_edge_destroyed_remains_safe(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _edge_destroyed_rows())
    report = run_lsr_v2_combined_risk_overlay(
        LSRV2CombinedRiskOverlaySettings(
            data_dir=str(tmp_path),
            max_drawdown_r=2.0,
            max_consecutive_losses_limit=2,
            min_profit_retention_ratio=0.90,
            min_trades_kept=40,
        )
    )
    assert report["status"] == "PASS"
    assert report["decision"] in {
        "KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_INSUFFICIENT",
        "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH",
        "KEEP_DIAGNOSTIC_LSR_V2_LOSS_STREAK_REMAINS_HIGH",
        "KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY",
        "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS",
    }
    assert report["promotion_ready"] is False
    assert report["positions_opened_by_lsr_v2_combined_overlay"] == 0


def test_duplicate_window_representations_are_deduped(tmp_path: Path):
    rows = []
    for row in _cluster_rows():
        rows.append(row)
        dup = dict(row)
        dup["window_size"] = 100000
        dup["window_label"] = "100k"
        rows.append(dup)
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", rows)
    report = run_lsr_v2_combined_risk_overlay(
        LSRV2CombinedRiskOverlaySettings(data_dir=str(tmp_path), min_trades_kept=40)
    )
    assert report["raw_trade_rows"] == len(rows)
    assert report["primary_trade_count"] == len(_cluster_rows()) // 2
    assert report["severe_trade_count"] == len(_cluster_rows()) // 2


def test_preflight_report_contains_best_overlay_and_no_promotion(tmp_path: Path):
    _write_jsonl(tmp_path / "lsr_v2_sample_expansion_trades.jsonl", _cluster_rows())
    report = run_lsr_v2_combined_risk_overlay(
        LSRV2CombinedRiskOverlaySettings(data_dir=str(tmp_path), min_trades_kept=40, max_consecutive_losses_limit=5)
    )
    preflight = json.loads(Path(report["operational_viability_preflight_report"]).read_text(encoding="utf-8"))
    assert preflight["best_combined_overlay"]
    assert preflight["promotion_ready"] is False
    assert preflight["orders_submitted_by_lsr_v2_operational_viability_preflight"] == 0
    trade_rows = Path(report["trades_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert len(trade_rows) > 0
