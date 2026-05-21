from core.cost_aware_meta import CostAwareMetaLabeler
from core.signal_density import SignalDensityMonitor


def main():
    est = CostAwareMetaLabeler.estimate(
        probability=60.0,
        rr_ratio=2.0,
        entry_price=100.0,
        stop_loss=99.0,
        atr_val=1.0,
        atr_ratio=1.0,
        atr_pct=1.0,
        entry_type="BREAKOUT",
    )
    assert est.gross_ev_r > 0.0
    assert est.expected_round_trip_cost_bps > 0.0
    assert est.expected_cost_r > 0.0
    assert est.expected_net_edge_r < est.gross_ev_r

    poor = CostAwareMetaLabeler.estimate(
        probability=40.0,
        rr_ratio=2.0,
        entry_price=100.0,
        stop_loss=99.0,
    )
    assert poor.expected_net_edge_r < est.expected_net_edge_r

    monitor = SignalDensityMonitor(meta_prob_threshold=55, meta_quality_threshold=50, enabled=True)
    monitor.observe_bar()
    monitor.observe_technical_candidate(side="BUY", tech_score=70, entry_type="BREAKOUT")
    monitor.observe_meta_decision(
        side="BUY",
        p_cal=60,
        setup_quality=70,
        tech_score=70,
        expected_value=est.gross_ev_r,
        expected_net_edge=est.expected_net_edge_r,
        expected_round_trip_cost_bps=est.expected_round_trip_cost_bps,
        cost_to_edge_ratio=est.cost_to_edge_ratio,
        cost_aware_accepted=est.accepted_cost_aware,
        is_tech_ok=True,
        ranked=True,
        accepted=True,
        regime="RANGING",
    )
    report = monitor.build_report()
    assert report["funnel"]["cost_aware_pass"] + report["funnel"]["cost_aware_fail"] == 1
    assert report["expected_net_edge_distribution"]["count"] == 1
    assert "cost_aware_threshold_optimization" in report
    print("Cost-aware meta-label diagnostics tests passed.")


if __name__ == "__main__":
    main()
