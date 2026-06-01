from __future__ import annotations

import json
import tempfile
from pathlib import Path

from types import SimpleNamespace

import core.edge_strategy_discovery as edge_discovery
from core.edge_strategy_discovery import (
    EdgeDiscoverySettings,
    archive_current_reports,
    build_edge_strategy_discovery_report,
    run_backtest_matrix,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _signal(meta: int, trades: int, cost_pass: int) -> dict:
    return {
        "funnel": {
            "bars_evaluated": 10000,
            "technical_candidates": 1000,
            "meta_accepted": meta,
            "pending_triggers_created": meta,
            "opened_trades": trades,
            "closed_trades": trades,
            "cost_aware_pass": cost_pass,
            "cost_aware_fail": 100,
        },
        "probability_distribution": {"max": 70.0, "median": 45.0, "p90": 60.0},
    }


def _archetype(alpha_avg_r: float, alpha_trades: int, beta_avg_r: float = -0.2) -> dict:
    return {
        "by_archetype": {
            "LIQUIDITY_SWEEP_REVERSAL": {
                "trades": alpha_trades,
                "wins": max(1, alpha_trades // 2),
                "partial_wins": 0,
                "losses": max(0, alpha_trades // 3),
                "breakevens": 0,
                "win_rate_pct": 60.0,
                "total_pnl": round(alpha_avg_r * alpha_trades, 4),
                "avg_pnl": alpha_avg_r,
                "avg_r": alpha_avg_r,
                "median_r": alpha_avg_r,
                "min_r": alpha_avg_r - 0.05,
                "max_r": alpha_avg_r + 0.1,
            },
            "RANGING_MEAN_REVERSION": {
                "trades": 10,
                "wins": 0,
                "partial_wins": 0,
                "losses": 7,
                "breakevens": 3,
                "win_rate_pct": 0.0,
                "total_pnl": beta_avg_r * 10,
                "avg_pnl": beta_avg_r,
                "avg_r": beta_avg_r,
                "median_r": beta_avg_r,
                "min_r": beta_avg_r - 0.1,
                "max_r": 0.0,
            },
        },
        "total_trades": alpha_trades + 10,
    }


def _readiness(status: str, pnl: float, trades: int) -> dict:
    return {
        "status": status,
        "net_pnl_pct": pnl,
        "max_drawdown_pct": 3.0,
        "closed_trades": trades,
        "blockers": [] if pnl > 0 else ["negative"],
        "warnings": [],
    }


def test_discovers_valid_edge_candidate_across_windows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        for label in ("10k", "12k", "15k"):
            _write(data / f"signal_density_{label}.json", _signal(meta=20, trades=10, cost_pass=200))
            _write(data / f"archetype_performance_{label}.json", _archetype(alpha_avg_r=0.22, alpha_trades=8))
            _write(data / f"paper_readiness_{label}.json", _readiness("RESEARCH_READY", 2.5, 18))
        settings = EdgeDiscoverySettings(
            data_dir=str(data),
            labels=("10k", "12k", "15k"),
            min_windows=3,
            min_positive_windows=3,
            min_total_trades=20,
            min_window_trades=3,
            min_weighted_avg_r=0.05,
        )
        report = build_edge_strategy_discovery_report(settings)
        assert report["status"] == "PASS"
        assert report["valid_strategy_count"] == 1
        assert report["valid_strategies"][0]["archetype"] == "LIQUIDITY_SWEEP_REVERSAL"
        assert report["valid_strategies"][0]["valid_edge"] is True
        blocked = [x for x in report["all_archetype_scores"] if x["archetype"] == "RANGING_MEAN_REVERSION"]
        assert blocked and blocked[0]["status"] == "BLOCKED_NEGATIVE_OR_UNSTABLE_EDGE"


def test_no_valid_strategy_when_long_window_negative() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        rows = {"10k": 0.2, "12k": 0.1, "15k": -0.4}
        for label, avg_r in rows.items():
            _write(data / f"signal_density_{label}.json", _signal(meta=20, trades=10, cost_pass=200))
            _write(data / f"archetype_performance_{label}.json", _archetype(alpha_avg_r=avg_r, alpha_trades=8))
            _write(data / f"paper_readiness_{label}.json", _readiness("NOT_READY" if avg_r < 0 else "RESEARCH_READY", avg_r * 10, 18))
        settings = EdgeDiscoverySettings(
            data_dir=str(data),
            labels=("10k", "12k", "15k"),
            min_windows=3,
            min_positive_windows=3,
            min_total_trades=20,
            min_window_trades=3,
            min_weighted_avg_r=0.05,
        )
        report = build_edge_strategy_discovery_report(settings)
        assert report["status"] == "WARN"
        assert report["valid_strategy_count"] == 0
        assert "negative_windows_present" in report["all_archetype_scores"][0]["blockers"]


def test_archives_reports_for_window_label() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        _write(data / "signal_density_report.json", _signal(meta=5, trades=3, cost_pass=10))
        _write(data / "archetype_performance_report.json", _archetype(alpha_avg_r=0.1, alpha_trades=3))
        copied = archive_current_reports(data, "10k")
        assert "signal_density_report.json" in copied
        assert (data / "signal_density_10k.json").exists()
        assert (data / "edge_strategy_runs" / "10k" / "archetype_performance_report.json").exists()


def test_backtest_matrix_streams_utf8_safe_subprocess_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        calls: list[dict] = []
        commands: list[list[str]] = []
        original_popen = edge_discovery.subprocess.Popen

        class FakeStdout:
            def __iter__(self):
                return iter(["OK UTF-8 output with emoji ✅ and arrows → ok\n"])

        class FakePopen:
            def __init__(self, command, **kwargs):
                commands.append(list(command))
                calls.append(kwargs)
                self.stdout = FakeStdout()
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                self.returncode = -9

        try:
            edge_discovery.subprocess.Popen = FakePopen  # type: ignore[assignment]
            settings = EdgeDiscoverySettings(
                data_dir=str(data),
                labels=("10k",),
                candle_windows=(10000,),
                timeout_seconds=5,
            )
            report = run_backtest_matrix(settings, project_root=Path(tmp), python_executable="python")
        finally:
            edge_discovery.subprocess.Popen = original_popen  # type: ignore[assignment]

        assert calls
        assert commands[0][1] == "-u"
        assert calls[0]["encoding"] == "utf-8"
        assert calls[0]["errors"] == "replace"
        assert calls[0]["text"] is True
        assert calls[0]["env"]["PYTHONUTF8"] == "1"
        assert calls[0]["env"]["PYTHONIOENCODING"] == "utf-8"
        log_path = data / "edge_strategy_runs" / "10k" / "backtest_stdout.txt"
        assert log_path.exists()
        assert "UTF-8 output" in log_path.read_text(encoding="utf-8")
        assert report["backtest_matrix"][0]["returncode"] == 0
        assert report["backtest_matrix"][0]["timed_out"] is False


def test_breakeven_drag_prunes_negative_mean_reversion_but_keeps_liquidity_watchlist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        for label in ("10k", "12k", "15k"):
            _write(data / f"signal_density_{label}.json", _signal(meta=20, trades=10, cost_pass=200))
            _write(
                data / f"archetype_performance_{label}.json",
                {
                    "by_archetype": {
                        "RANGING_MEAN_REVERSION": {
                            "trades": 20,
                            "wins": 2,
                            "partial_wins": 0,
                            "losses": 5,
                            "breakevens": 13,
                            "win_rate_pct": 28.57,
                            "total_pnl": -1.5,
                            "avg_pnl": -0.075,
                            "avg_r": -0.15,
                            "median_r": -0.12,
                            "min_r": -1.1,
                            "max_r": 0.2,
                        },
                        "LIQUIDITY_SWEEP_REVERSAL": {
                            "trades": 4,
                            "wins": 2,
                            "partial_wins": 0,
                            "losses": 1,
                            "breakevens": 1,
                            "win_rate_pct": 66.67,
                            "total_pnl": 2.2,
                            "avg_pnl": 0.55,
                            "avg_r": 0.61,
                            "median_r": 0.6,
                            "min_r": -0.5,
                            "max_r": 1.7,
                        },
                    },
                    "total_trades": 24,
                },
            )
            _write(data / f"paper_readiness_{label}.json", _readiness("NOT_READY", -1.0, 24))
        settings = EdgeDiscoverySettings(
            data_dir=str(data),
            labels=("10k", "12k", "15k"),
            min_windows=3,
            min_positive_windows=3,
            min_total_trades=20,
            min_window_trades=3,
            min_weighted_avg_r=0.05,
            max_breakeven_drag_ratio=0.45,
            min_prune_trades=20,
        )
        report = build_edge_strategy_discovery_report(settings)
        pruning = report["pruning_recommendations"]
        assert report["decision"] == edge_discovery.PRUNING_REQUIRED_DECISION
        assert "RANGING_MEAN_REVERSION" in pruning["hard_block_archetypes"]
        assert "RANGING_MEAN_REVERSION" in pruning["breakeven_drag_archetypes"]
        assert "LIQUIDITY_SWEEP_REVERSAL" not in pruning["hard_block_archetypes"]
        assert report["breakeven_drag_summary"]["blocked_by_breakeven_drag"] == ["RANGING_MEAN_REVERSION"]
        row = [x for x in report["all_archetype_scores"] if x["archetype"] == "RANGING_MEAN_REVERSION"][0]
        assert row["breakeven_ratio"] > 0.6
        assert row["prune_recommended"] is True


if __name__ == "__main__":
    test_discovers_valid_edge_candidate_across_windows()
    test_no_valid_strategy_when_long_window_negative()
    test_archives_reports_for_window_label()
    test_backtest_matrix_streams_utf8_safe_subprocess_output()
    test_breakeven_drag_prunes_negative_mean_reversion_but_keeps_liquidity_watchlist()
    print("Edge strategy discovery tests passed.")
