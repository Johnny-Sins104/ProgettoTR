import json
import os
import tempfile

import pandas as pd

from core.walk_forward import WalkForwardPipeline


def main():
    df = pd.DataFrame(index=pd.date_range("2024-01-01", periods=1200, freq="15min"))
    df["market_regime"] = ["TRENDING" if i % 3 == 0 else "RANGING" for i in range(len(df))]

    splits = WalkForwardPipeline.get_wf_splits(
        total_len=len(df),
        N=500,
        M=100,
        embargo_gap=25,
        label_horizon=50,
        df=df,
    )
    assert splits, "Expected at least one walk-forward split"

    for fold in splits:
        WalkForwardPipeline.validate_fold(fold)
        assert fold.effective_train_end + fold.label_horizon < fold.test_start
        assert fold.embargo_start == fold.train_end + 1
        assert fold.embargo_end == fold.test_start - 1
        assert fold.effective_train_size > 0
        assert fold.effective_test_size > 0

    report = WalkForwardPipeline.build_audit_report(
        splits=splits,
        total_len=len(df),
        requested_train_size=500,
        test_size=100,
        embargo_gap=25,
        label_horizon=50,
        df=df,
    )
    assert report["status"] == "PASS"
    assert report["fold_count"] == len(splits)
    assert report["purged_samples_total"] > 0
    assert "regime_distributions" in report

    short_splits = WalkForwardPipeline.get_wf_splits(
        total_len=1000,
        N=2000,
        M=500,
        embargo_gap=100,
        label_horizon=100,
    )
    short_report = WalkForwardPipeline.build_audit_report(
        splits=short_splits,
        total_len=1000,
        requested_train_size=2000,
        test_size=500,
        embargo_gap=100,
        label_horizon=100,
    )
    assert short_report["status"] == "NO_SPLITS"
    assert short_report["insufficient_data"] is True
    assert short_report["warnings"], "Expected explicit insufficient-data warning"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "walkforward_audit_report.json")
        WalkForwardPipeline.export_audit_report(report, path)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["status"] == "PASS"

    print("Walk-forward audit tests passed.")


if __name__ == "__main__":
    main()
