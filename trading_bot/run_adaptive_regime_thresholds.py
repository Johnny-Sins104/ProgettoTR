from pathlib import Path
import json

from core.signal_density import SignalDensityMonitor
from core.adaptive_regime_thresholds import AdaptiveRegimeThresholdOptimizer
from config import Config


def main() -> None:
    report_path = Path(Config.SIGNAL_DENSITY_REPORT_PATH)
    if not report_path.exists():
        raise SystemExit(
            f"Signal density report not found: {report_path}. Run run_custom_backtest.py first."
        )
    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    samples = report.get("sample_accepted_setups", []) + report.get("sample_rejected_setups", [])
    # If the full report only stores first 25 rejected samples, use what exists; for
    # complete analysis, rely on the backtest-integrated report produced directly.
    if not samples:
        raise SystemExit("No samples found in signal_density_report.json")
    out = AdaptiveRegimeThresholdOptimizer.export_report(
        samples,
        Config.ADAPTIVE_REGIME_THRESHOLD_REPORT_PATH,
        min_trades_per_regime=Config.ADAPTIVE_REGIME_MIN_TRADES,
    )
    print("[AdaptiveRegimeThresholds] Completed")
    print(f"  Samples : {out.get('samples')}")
    print(f"  Output  : {Config.ADAPTIVE_REGIME_THRESHOLD_REPORT_PATH}")
    for regime, info in out.get("regimes", {}).items():
        best = info.get("best_threshold") or {}
        print(
            f"  {regime:<12} samples={info.get('samples',0):<5} "
            f"positive={info.get('positive_net_edge_samples',0):<5} "
            f"best=p>={best.get('probability_threshold')} q>={best.get('quality_threshold')} "
            f"pass={best.get('selected_count')} avg_net={best.get('avg_expected_net_edge_r')} status={best.get('status')}"
        )


if __name__ == "__main__":
    main()
