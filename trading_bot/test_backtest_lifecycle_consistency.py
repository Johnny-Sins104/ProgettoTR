"""Smoke tests for dependency-light backtest lifecycle utilities."""
from pathlib import Path
import json
import tempfile

from core.backtest_lifecycle import canonical_trade_pnl, write_lifecycle_report


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lifecycle_consistency_report.json"
        charts = Path(tmp) / "charts"
        charts.mkdir()
        (charts / "trade_001_LOSS.html").write_text("x", encoding="utf-8")
        (charts / "trade_002_WIN.html").write_text("x", encoding="utf-8")

        result = {
            "trades": [
                {"realized_pnl": 5.0, "balance_before": 100.0, "balance_after": 105.0, "balance": 105.0},
                {"pnl": -2.0, "balance_before": 105.0, "balance_after": 103.0, "balance": 103.0},
            ],
            "risk_events": 2,
            "risk_bearing_snapshots": 2,
        }
        report = write_lifecycle_report(result, str(charts), str(out))
        assert report["status"] == "PASS", report
        assert report["closed_trades"] == 2, report
        assert report["risk_events"] == 2, report
        assert report["balance_mutation_mismatches"] == 0, report
        assert out.exists(), "lifecycle report was not created"
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["closed_equals_risk_events"] is True

        bad_result = dict(result)
        bad_result["risk_events"] = 1
        bad_report = write_lifecycle_report(bad_result, str(charts), str(out))
        assert bad_report["status"] == "WARN", bad_report

        assert canonical_trade_pnl({"pnl_eur": 1.25}) == 1.25
        assert canonical_trade_pnl({"realized_pnl": 2.5, "pnl": 0.0}) == 2.5

    print("Backtest lifecycle consistency tests passed.")


if __name__ == "__main__":
    main()
