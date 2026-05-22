from core.setup_engine import MarketStructureSetupEngine
from core.setup_filter import SetupFilter
from core.signal_density import SignalDensityMonitor


def test_liquidity_sweep_quality_boost():
    row = {
        "Close": 100.0,
        "ema_200": 99.0,
        "rsi_14": 38.0,
        "Volume": 1000.0,
        "sweep_low": 1.0,
        "sweep_high": 0.0,
        "liquidity_sweep_score": 0.003,
        "market_regime": "RANGING",
        "session_london": 1.0,
        "session_overlap_london_ny": 1.0,
        "htf_4h_trend": 1.0,
        "volatility_compression": 0.8,
    }
    legacy = SetupFilter.calculate_legacy_quality_score(row, 1.1, "BUY")
    details = SetupFilter.calculate_quality_details(row, 1.1, "BUY")
    assert details["setup_quality"] >= legacy
    assert details["structure_score"] > 20
    assert details["setup_archetype"] in {
        "LIQUIDITY_SWEEP_REVERSAL",
        "RANGING_MEAN_REVERSION",
        "HTF_ALIGNED_PULLBACK",
    }


def test_invalid_side_rejected():
    res = MarketStructureSetupEngine.evaluate({}, "HOLD", 50.0)
    assert res.archetype == "INVALID"
    assert res.enhanced_quality == 0.0


def test_signal_density_records_archetype():
    mon = SignalDensityMonitor(meta_prob_threshold=55, meta_quality_threshold=50)
    mon.observe_meta_decision(
        side="BUY",
        p_cal=60,
        setup_quality=62,
        tech_score=75,
        expected_value=0.2,
        expected_net_edge=0.1,
        expected_round_trip_cost_bps=10,
        cost_to_edge_ratio=0.3,
        cost_aware_accepted=True,
        is_tech_ok=True,
        ranked=True,
        accepted=True,
        regime="RANGING",
        setup_archetype="LIQUIDITY_SWEEP_REVERSAL",
        structure_score=68,
        edge_adjustment_r=0.03,
    )
    report = mon.build_report()
    assert report["setup_archetype_counts"]["LIQUIDITY_SWEEP_REVERSAL"] == 1
    assert report["structure_score_distribution"]["count"] == 1


def main():
    test_liquidity_sweep_quality_boost()
    test_invalid_side_rejected()
    test_signal_density_records_archetype()
    print("Setup engine refactor tests passed.")


if __name__ == "__main__":
    main()
