from pathlib import Path
import json
import tempfile

from core.signal_density import SignalDensityMonitor


def main():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "signal_density_report.json"
        m = SignalDensityMonitor(meta_prob_threshold=55.0, meta_quality_threshold=50.0, output_path=path)
        for _ in range(10):
            m.observe_bar()
        m.observe_no_technical_candidate()
        m.observe_technical_candidate(side="BUY", tech_score=72, entry_type="BREAKOUT")
        m.observe_meta_decision(
            side="BUY",
            p_cal=40.7,
            setup_quality=65.0,
            tech_score=72.0,
            expected_value=0.221,
            is_tech_ok=True,
            ranked=True,
            accepted=False,
            regime="RANGING",
        )
        m.observe_technical_candidate(side="SELL", tech_score=80, entry_type="BREAKOUT")
        m.observe_meta_decision(
            side="SELL",
            p_cal=62.0,
            setup_quality=70.0,
            tech_score=80.0,
            expected_value=0.86,
            is_tech_ok=True,
            ranked=True,
            accepted=True,
            regime="TRENDING",
        )
        m.observe_pending_created()
        m.observe_pending_filled()
        m.observe_opened_trade()
        m.closed_trades = 1
        report = m.export()
        assert path.exists()
        payload = json.loads(path.read_text())
        assert report["funnel"]["technical_candidates"] == 2
        assert report["funnel"]["meta_accepted"] == 1
        assert report["funnel"]["opened_trades"] == 1
        assert "probability_distribution" in payload
        assert len(payload["threshold_sweep"]) > 0
    print("Signal density diagnostics tests passed.")


if __name__ == "__main__":
    main()
