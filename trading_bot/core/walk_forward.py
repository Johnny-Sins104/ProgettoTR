"""
Walk-forward validation utilities.

This module builds purged walk-forward splits for financial ML.  The key
statistical rule is that no training sample whose label horizon can overlap the
validation window may remain in the effective training set.  The train window is
therefore separated from the test window by an embargo gap and the effective
training samples are further purged by label_horizon.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json
import os

import pandas as pd


@dataclass
class WalkForwardFold:
    """Single purged walk-forward split with explicit boundary metadata."""

    fold_idx: int
    train_start: int
    train_end: int
    embargo_start: int
    embargo_end: int
    test_start: int
    test_end: int

    train_start_time: Optional[pd.Timestamp] = None
    train_end_time: Optional[pd.Timestamp] = None
    embargo_start_time: Optional[pd.Timestamp] = None
    embargo_end_time: Optional[pd.Timestamp] = None
    test_start_time: Optional[pd.Timestamp] = None
    test_end_time: Optional[pd.Timestamp] = None

    label_horizon: int = 100
    effective_train_start: int = 0
    effective_train_end: int = 0
    num_purged_samples: int = 0
    effective_train_size: int = 0
    effective_test_size: int = 0
    train_mode: str = "expanding"

    def to_dict(self) -> Dict[str, Union[int, str, None]]:
        return {
            "fold_idx": self.fold_idx,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "effective_train_start": self.effective_train_start,
            "effective_train_end": self.effective_train_end,
            "embargo_start": self.embargo_start,
            "embargo_end": self.embargo_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_start_time": str(self.train_start_time) if self.train_start_time is not None else None,
            "train_end_time": str(self.train_end_time) if self.train_end_time is not None else None,
            "embargo_start_time": str(self.embargo_start_time) if self.embargo_start_time is not None else None,
            "embargo_end_time": str(self.embargo_end_time) if self.embargo_end_time is not None else None,
            "test_start_time": str(self.test_start_time) if self.test_start_time is not None else None,
            "test_end_time": str(self.test_end_time) if self.test_end_time is not None else None,
            "label_horizon": self.label_horizon,
            "num_purged_samples": self.num_purged_samples,
            "effective_train_size": self.effective_train_size,
            "effective_test_size": self.effective_test_size,
            "train_mode": self.train_mode,
        }


class WalkForwardPipeline:
    @staticmethod
    def _ts(df: Optional[pd.DataFrame], idx: int) -> Optional[pd.Timestamp]:
        if df is None or not isinstance(df.index, pd.DatetimeIndex):
            return None
        if idx < 0 or idx >= len(df):
            return None
        return df.index[idx]

    @staticmethod
    def get_wf_splits(
        total_len: int,
        N: int = 2000,
        M: int = 500,
        embargo_gap: int = 100,
        train_mode: str = "expanding",
        df: Optional[pd.DataFrame] = None,
        label_horizon: int = 100,
        min_train_size: int = 30,
    ) -> List[WalkForwardFold]:
        """
        Build purged walk-forward splits.

        Parameters
        ----------
        total_len:
            Number of chronological observations.
        N:
            Training anchor/window size.  In expanding mode the first test starts
            at N.  In rolling mode the train window length is at most N.
        M:
            Test-window size and step between consecutive folds.
        embargo_gap:
            Number of candles between train_end and test_start.
        label_horizon:
            Number of future candles used by labels.  The final label_horizon
            samples inside each train window are purged from effective training.
        min_train_size:
            Minimum effective training samples required to keep a fold.
        """
        if total_len <= 0:
            return []
        if N <= 0 or M <= 0:
            raise ValueError("N and M must be positive integers")
        if embargo_gap < 0 or label_horizon < 0:
            raise ValueError("embargo_gap and label_horizon must be non-negative")
        if train_mode not in {"expanding", "rolling"}:
            raise ValueError("train_mode must be 'expanding' or 'rolling'")
        if total_len <= N:
            return []

        splits: List[WalkForwardFold] = []
        fold_idx = 1

        for test_start in range(N, total_len, M):
            train_end = test_start - 1 - embargo_gap
            if train_end < 0:
                continue

            if train_mode == "rolling":
                train_start = max(0, train_end - N + 1)
            else:
                train_start = 0

            effective_train_end = train_end - label_horizon
            effective_train_start = train_start
            effective_train_size = max(0, effective_train_end - effective_train_start + 1)
            if effective_train_size < min_train_size:
                continue

            test_end = min(test_start + M - 1, total_len - 1)
            embargo_start = train_end + 1
            embargo_end = test_start - 1
            num_purged_samples = min(label_horizon, max(0, train_end - train_start + 1))

            fold = WalkForwardFold(
                fold_idx=fold_idx,
                train_start=train_start,
                train_end=train_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                test_start=test_start,
                test_end=test_end,
                train_start_time=WalkForwardPipeline._ts(df, train_start),
                train_end_time=WalkForwardPipeline._ts(df, train_end),
                embargo_start_time=WalkForwardPipeline._ts(df, embargo_start),
                embargo_end_time=WalkForwardPipeline._ts(df, embargo_end),
                test_start_time=WalkForwardPipeline._ts(df, test_start),
                test_end_time=WalkForwardPipeline._ts(df, test_end),
                label_horizon=label_horizon,
                effective_train_start=effective_train_start,
                effective_train_end=effective_train_end,
                num_purged_samples=num_purged_samples,
                effective_train_size=effective_train_size,
                effective_test_size=(test_end - test_start + 1),
                train_mode=train_mode,
            )
            WalkForwardPipeline.validate_fold(fold)
            splits.append(fold)
            fold_idx += 1

        return splits

    @staticmethod
    def validate_fold(fold: WalkForwardFold) -> None:
        """Hard assertions for no train/test overlap and label-horizon purging."""
        if fold.train_start > fold.effective_train_start:
            raise ValueError("effective train start cannot precede declared train start")
        if fold.effective_train_end > fold.train_end:
            raise ValueError("effective train end cannot exceed train_end")
        if fold.effective_train_end + fold.label_horizon > fold.train_end:
            raise ValueError("label horizon purge is not respected")
        if fold.train_end >= fold.embargo_start:
            raise ValueError("train_end must be before embargo_start")
        if fold.embargo_end >= fold.test_start:
            raise ValueError("embargo_end must be before test_start")
        if fold.train_end >= fold.test_start:
            raise ValueError("train/test overlap detected")
        label_end = fold.effective_train_end + fold.label_horizon
        if label_end >= fold.test_start:
            raise ValueError("label horizon overlaps or touches test window")
        if fold.effective_train_size <= 0:
            raise ValueError("effective train size must be positive")
        if fold.effective_test_size <= 0:
            raise ValueError("effective test size must be positive")

    @staticmethod
    def build_audit_report(
        splits: List[WalkForwardFold],
        total_len: int,
        requested_train_size: int,
        test_size: int,
        embargo_gap: int,
        label_horizon: int,
        train_mode: str = "expanding",
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """Generate machine-readable split diagnostics for quant validation."""
        insufficient_data = total_len <= requested_train_size
        report: Dict[str, Any] = {
            "status": "PASS" if splits else "NO_SPLITS",
            "total_len": int(total_len),
            "requested_train_size": int(requested_train_size),
            "test_size": int(test_size),
            "embargo_gap": int(embargo_gap),
            "label_horizon": int(label_horizon),
            "train_mode": train_mode,
            "fold_count": len(splits),
            "insufficient_data": bool(insufficient_data),
            "minimum_required_candles": int(requested_train_size + test_size),
            "warnings": [],
            "folds": [fold.to_dict() for fold in splits],
        }
        if insufficient_data:
            report["warnings"].append(
                "No walk-forward split was generated because total_len <= requested_train_size. "
                "This means the current backtest is not performing true OOS walk-forward validation."
            )
        if not splits and not insufficient_data:
            report["warnings"].append("No valid fold survived purge/embargo/min_train_size constraints.")
        if splits:
            report["effective_train_size_min"] = min(f.effective_train_size for f in splits)
            report["effective_train_size_max"] = max(f.effective_train_size for f in splits)
            report["effective_test_size_min"] = min(f.effective_test_size for f in splits)
            report["effective_test_size_max"] = max(f.effective_test_size for f in splits)
            report["purged_samples_total"] = sum(f.num_purged_samples for f in splits)
        if df is not None and "market_regime" in df.columns and splits:
            regime_rows = []
            for fold in splits:
                train_reg = df.iloc[fold.effective_train_start:fold.effective_train_end + 1]["market_regime"].value_counts().to_dict()
                test_reg = df.iloc[fold.test_start:fold.test_end + 1]["market_regime"].value_counts().to_dict()
                regime_rows.append({
                    "fold_idx": fold.fold_idx,
                    "regime_distribution_train": {str(k): int(v) for k, v in train_reg.items()},
                    "regime_distribution_test": {str(k): int(v) for k, v in test_reg.items()},
                })
            report["regime_distributions"] = regime_rows
        return report

    @staticmethod
    def export_audit_report(report: Dict[str, Any], path: str = "data/walkforward_audit_report.json") -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [WalkForwardAudit] Report exported -> {path}  ({report.get('status')})")

    @staticmethod
    def audit_and_export(
        total_len: int,
        N: int = 2000,
        M: int = 500,
        embargo_gap: int = 100,
        train_mode: str = "expanding",
        df: Optional[pd.DataFrame] = None,
        label_horizon: int = 100,
        path: str = "data/walkforward_audit_report.json",
    ) -> List[WalkForwardFold]:
        splits = WalkForwardPipeline.get_wf_splits(
            total_len=total_len,
            N=N,
            M=M,
            embargo_gap=embargo_gap,
            train_mode=train_mode,
            df=df,
            label_horizon=label_horizon,
        )
        report = WalkForwardPipeline.build_audit_report(
            splits=splits,
            total_len=total_len,
            requested_train_size=N,
            test_size=M,
            embargo_gap=embargo_gap,
            label_horizon=label_horizon,
            train_mode=train_mode,
            df=df,
        )
        WalkForwardPipeline.export_audit_report(report, path=path)
        return splits

    @staticmethod
    def print_timeline(splits: List[WalkForwardFold], total_len: int):
        if not splits:
            print("⚠️ Nessun split walk-forward da visualizzare.")
            return

        print("\n" + "=" * 80)
        print(" 📅 TIMELINE DEL PIPELINE DI VALIDAZIONE WALK-FORWARD (PURGED + EMBARGO)")
        print("=" * 80)

        bar_len = 40
        for fold in splits:
            t_start_ratio = int((fold.effective_train_start / total_len) * bar_len)
            t_end_ratio = int((fold.effective_train_end / total_len) * bar_len)
            emb_start_ratio = int((fold.embargo_start / total_len) * bar_len)
            emb_end_ratio = int((fold.embargo_end / total_len) * bar_len)
            test_start_ratio = int((fold.test_start / total_len) * bar_len)
            test_end_ratio = int((fold.test_end / total_len) * bar_len)

            line = ["."] * bar_len
            for i in range(t_start_ratio, min(t_end_ratio + 1, bar_len)):
                line[i] = "T"
            for i in range(max(t_end_ratio + 1, emb_start_ratio), min(emb_end_ratio + 1, bar_len)):
                line[i] = "E"
            for i in range(max(emb_end_ratio + 1, test_start_ratio), min(test_end_ratio + 1, bar_len)):
                line[i] = "V"

            dates_str = ""
            if fold.train_start_time is not None and fold.test_end_time is not None:
                dates_str = f" ({fold.train_start_time.strftime('%y-%m-%d')} a {fold.test_end_time.strftime('%y-%m-%d')})"

            print(
                f"  Fold {fold.fold_idx:02d}: |{''.join(line)}| "
                f"effective train {fold.effective_train_start}->{fold.effective_train_end} | "
                f"embargo {fold.embargo_start}->{fold.embargo_end} | "
                f"test {fold.test_start}->{fold.test_end}{dates_str}"
            )

        print("\n  Legenda: [T] = Effective Train | [E] = Embargo | [V] = Out-of-Sample Test")
        print("=" * 80 + "\n")
