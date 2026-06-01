from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.lsr_v2_trade_forensics import LSRV2TradeForensicsSettings, parse_windows, run_lsr_v2_trade_forensics


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _trade(*, idx: int, window: int, model: str, net_r: float, gross_r: float | None = None, side: str = "BUY", reason: str = "TAKE_PROFIT") -> dict:
    gross = net_r + (0.05 if model == "conservative" else 0.25) if gross_r is None else gross_r
    return {
        "event_type": "LSR_V2_BACKTEST_TRADE",
        "candidate_id": f"cand_{idx}",
        "window_size": window,
        "window_label": f"{window // 1000}k" if window % 1000 == 0 else str(window),
        "cost_model": model,
        "side": side,
        "entry_index": idx * 10,
        "exit_index": idx * 10 + 3,
        "entry_timestamp": f"2026-05-28T00:{idx % 60:02d}:00+00:00",
        "exit_timestamp": f"2026-05-28T00:{(idx + 3) % 60:02d}:00+00:00",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "exit_price": 102.0 if net_r > 0 else 99.0,
        "exit_reason": reason,
        "gross_r": gross,
        "cost_r": gross - net_r,
        "net_r": net_r,
        "net_pnl": net_r * 2.5,
        "quality_grade": "A",
        "regime": "RANGING",
        "orders_submitted_by_lsr_v2_backtest": 0,
        "positions_opened_by_lsr_v2_backtest": 0,
    }


def test_parse_windows_accepts_k_labels():
    assert parse_windows("10k,12000,15K") == (10000, 12000, 15000)


def test_forensics_no_trade_files_returns_warn(tmp_path: Path):
    report = run_lsr_v2_trade_forensics(LSRV2TradeForensicsSettings(data_dir=str(tmp_path / "data"), windows=(10000,), primary_windows=(10000,)))
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_FORENSICS_NO_TRADES"
    assert report["orders_submitted_by_lsr_v2_forensics"] == 0
    assert report["positions_opened_by_lsr_v2_forensics"] == 0
    assert report["promotion_ready"] is False


def test_forensics_detects_low_sample_outlier_and_cost_sensitive_edge(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows: list[dict] = []
    # Conservative primary rows: positive but low sample and outlier-dominated.
    conservative_r = [3.0, 0.7, 0.5, -0.4, -0.2]
    severe_r = [-0.2, 0.1, -0.1, -0.6, -0.4]
    for i, (cons, severe) in enumerate(zip(conservative_r, severe_r)):
        rows.append(_trade(idx=i, window=10000, model="conservative", net_r=cons, side="BUY" if i % 2 == 0 else "SELL"))
        rows.append(_trade(idx=i, window=10000, model="severe", net_r=severe, side="BUY" if i % 2 == 0 else "SELL"))
    _write_jsonl(data_dir / "lsr_v2_trades_10k.jsonl", rows)
    (data_dir / "lsr_v2_backtest_matrix_report.json").write_text(json.dumps({
        "criteria": {"blockers": ["closed_trades_below_minimum", "top_trade_concentration_not_ok", "severe_cost_survival_not_ok"]}
    }), encoding="utf-8")

    report = run_lsr_v2_trade_forensics(LSRV2TradeForensicsSettings(data_dir=str(data_dir), windows=(10000,), primary_windows=(10000,)))
    assert report["status"] == "PASS"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE"
    assert report["primary_closed_trades"] == 5
    assert "FRAGILE_POSITIVE_EDGE" in report["classification_labels"]
    assert "LOW_SAMPLE_EDGE" in report["classification_labels"]
    assert "OUTLIER_DOMINATED_EDGE" in report["classification_labels"]
    assert "COST_SENSITIVE_EDGE" in report["classification_labels"]
    assert report["promotion_ready"] is False
    assert Path(report["by_window_report"]).exists()
    assert Path(report["cost_failure_report"]).exists()


def test_forensics_can_mark_research_ready_for_walk_forward_when_not_fragile(tmp_path: Path):
    data_dir = tmp_path / "data"
    windows = (10000, 12000, 15000)
    for window in windows:
        rows: list[dict] = []
        for i in range(12):
            # diversified positive edge, no single top trade dominates.
            net = 0.45 if i % 3 != 0 else -0.18
            rows.append(_trade(idx=i + window, window=window, model="conservative", net_r=net, side="BUY" if i % 2 else "SELL"))
            rows.append(_trade(idx=i + window, window=window, model="severe", net_r=net - 0.08, side="BUY" if i % 2 else "SELL"))
        _write_jsonl(data_dir / f"lsr_v2_trades_{window // 1000}k.jsonl", rows)
    report = run_lsr_v2_trade_forensics(LSRV2TradeForensicsSettings(
        data_dir=str(data_dir),
        windows=windows,
        primary_windows=windows,
        min_closed_trades=30,
        min_positive_windows=3,
        max_top1_positive_concentration=0.45,
        max_top3_positive_concentration=0.80,
        severe_degradation_warn_r=10.0,
        cost_flip_warn_ratio=0.50,
    ))
    assert report["decision"] == "LSR_V2_FORENSICS_READY_DIAGNOSTIC"
    assert report["classification_labels"] == ["RESEARCH_READY_FOR_WALK_FORWARD"]
    assert report["promotion_ready"] is False


def test_cost_failure_report_counts_win_to_nonwin(tmp_path: Path):
    data_dir = tmp_path / "data"
    rows = [
        _trade(idx=1, window=10000, model="conservative", net_r=0.8),
        _trade(idx=1, window=10000, model="severe", net_r=-0.2),
        _trade(idx=2, window=10000, model="conservative", net_r=0.6),
        _trade(idx=2, window=10000, model="severe", net_r=0.4),
    ]
    _write_jsonl(data_dir / "lsr_v2_trades_10k.jsonl", rows)
    report = run_lsr_v2_trade_forensics(LSRV2TradeForensicsSettings(data_dir=str(data_dir), windows=(10000,), primary_windows=(10000,), min_closed_trades=1))
    cost_report = json.loads(Path(report["cost_failure_report"]).read_text(encoding="utf-8"))
    assert cost_report["paired_trade_count"] == 2
    assert cost_report["win_to_nonwin_under_severe_count"] == 1
    assert cost_report["by_bucket"]["conservative_win_to_severe_loss"] == 1
