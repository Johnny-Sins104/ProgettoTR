from pathlib import Path
import json
import tempfile

from core.adaptive_regime_thresholds import AdaptiveRegimeThresholdOptimizer
from core.signal_density import SignalDensityMonitor


def main() -> None:
    samples = [
        {"regime": "TRENDING", "p_cal": 42, "setup_quality": 32, "expected_net_edge_r": 0.12, "expected_round_trip_cost_bps": 10},
        {"regime": "TRENDING", "p_cal": 45, "setup_quality": 35, "expected_net_edge_r": 0.20, "expected_round_trip_cost_bps": 11},
        {"regime": "TRENDING", "p_cal": 60, "setup_quality": 50, "expected_net_edge_r": -0.10, "expected_round_trip_cost_bps": 15},
        {"regime": "RANGING", "p_cal": 35, "setup_quality": 30, "expected_net_edge_r": 0.05, "expected_round_trip_cost_bps": 8},
        {"regime": "RANGING", "p_cal": 38, "setup_quality": 34, "expected_net_edge_r": 0.07, "expected_round_trip_cost_bps": 8},
        {"regime": "HIGH_VOL", "p_cal": 70, "setup_quality": 60, "expected_net_edge_r": -0.50, "expected_round_trip_cost_bps": 30},
    ]
    report = AdaptiveRegimeThresholdOptimizer.build_report(samples, min_trades_per_regime=2)
    assert report["samples"] == 6
    assert "TRENDING" in report["regimes"]
    assert "RANGING" in report["regimes"]
    assert report["regimes"]["TRENDING"]["positive_net_edge_samples"] == 2
    assert report["regimes"]["RANGING"]["best_threshold"]["selected_count"] >= 2

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "adaptive.json"
        AdaptiveRegimeThresholdOptimizer.export_report(samples, out, min_trades_per_regime=2)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["mode"] == "diagnostic_only"

    mon = SignalDensityMonitor(meta_prob_threshold=55, meta_quality_threshold=50)
    for s in samples:
        mon.observe_meta_decision(
            side="BUY",
            p_cal=s["p_cal"],
            setup_quality=s["setup_quality"],
            tech_score=s["setup_quality"],
            expected_value=s["expected_net_edge_r"],
            expected_net_edge=s["expected_net_edge_r"],
            expected_round_trip_cost_bps=s["expected_round_trip_cost_bps"],
            cost_to_edge_ratio=0.2,
            cost_aware_accepted=s["expected_net_edge_r"] > 0,
            is_tech_ok=True,
            ranked=s["expected_net_edge_r"] > 0,
            accepted=False,
            regime=s["regime"],
        )
    full = mon.build_report()
    assert "adaptive_regime_threshold_optimization" in full
    assert full["adaptive_regime_threshold_optimization"]["regimes"]
    print("Adaptive regime threshold tests passed.")


if __name__ == "__main__":
    main()
