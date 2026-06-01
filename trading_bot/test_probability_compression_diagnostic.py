from __future__ import annotations

import json
from pathlib import Path
import tempfile

from core.probability_compression_diagnostic import (
    ProbabilityCompressionDiagnosticSettings,
    build_probability_compression_report,
)


def _write(path: Path, *, maxp: float, cost_pass: int, meta: int, trades: int) -> None:
    path.write_text(json.dumps({
        "funnel": {
            "bars_evaluated": 19999,
            "technical_candidates": 4460,
            "cost_aware_pass": cost_pass,
            "cost_aware_fail": 3406,
            "meta_accepted": meta,
            "pending_triggers_created": meta,
            "opened_trades": trades,
        },
        "probability_distribution": {"median": 33.0, "p90": 42.0, "max": maxp},
        "cost_aware_threshold_optimization": [
            {"prob_threshold": 50, "quality_threshold": 30, "would_pass": 49, "avg_expected_net_edge_r": 0.28}
        ],
    }), encoding="utf-8")


def test_probability_compression_flags_cost_pass_without_meta_acceptance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d / "signal_density_18k.json", maxp=80.0, cost_pass=100, meta=10, trades=5)
        _write(d / "signal_density_20k.json", maxp=50.0, cost_pass=1054, meta=0, trades=0)
        report = build_probability_compression_report(
            settings=ProbabilityCompressionDiagnosticSettings(data_dir=str(d), labels=("18k", "20k")),
            write_report=False,
        )
        assert report["status"] == "WARN"
        assert report["compression_detected"] is True
        assert report["compression_labels"] == ["20k"]
        assert "20k" in report["probability_gate_impossible_labels"]


if __name__ == "__main__":
    test_probability_compression_flags_cost_pass_without_meta_acceptance()
    print("Probability compression diagnostic tests passed.")
