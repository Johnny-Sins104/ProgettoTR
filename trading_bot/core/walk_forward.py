"""
Walk-forward validation utilities.

Prompt 28 upgrade
-----------------
Builds purged walk-forward splits with two operating modes:

1. research/default mode, using the requested train/test sizes;
2. adaptive rolling mode, which shrinks train/test windows on short local
   backtests while preserving the statistical invariants: no train/test overlap,
   label-horizon purge and embargo separation.

The adaptive path prevents the invalid diagnostic state where a 1,000 candle
smoke test reports NO_SPLITS only because the default train window is 2,000.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json

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
    train_mode: str = "rolling"
    adaptive: bool = False

    def to_dict(self) -> Dict[str, Union[int, str, None, bool]]:
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
            "adaptive": self.adaptive,
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
    def _sanitize_sizes(
        total_len: int,
        N: int,
        M: int,
        embargo_gap: int,
        label_horizon: int,
        min_train_size: int,
        min_test_size: int,
        adaptive: bool,
    ) -> tuple[int, int, int, bool, list[str]]:
        warnings: list[str] = []
        if total_len <= 0:
            return N, M, min_train_size, False, warnings
        if not adaptive:
            return N, M, min_train_size, False, warnings

        # Earliest feasible test start with purge+embargo intact:
        # effective train size + label horizon + embargo.
        min_feasible_start = int(min_train_size + label_horizon + embargo_gap)
        if total_len <= min_feasible_start + max(1, min_test_size // 2):
            # Last-resort smoke-test mode: reduce minimum train/test but do not
            # violate purge or embargo.  This is marked adaptive in the audit.
            min_train_size = max(30, int(total_len * 0.25))
            min_test_size = max(20, int(total_len * 0.10))
            min_feasible_start = int(min_train_size + label_horizon + embargo_gap)
            warnings.append(
                "Adaptive WF reduced min_train_size/min_test_size because the local sample is very short."
            )

        if total_len <= N:
            target_test_size = max(min_test_size, min(M, max(min_test_size, total_len // 5)))
            # Put first test start late enough for a useful train window, but
            # leave room for at least one test window.
            adaptive_N = min(
                max(min_feasible_start, int(total_len * 0.60)),
                max(min_feasible_start, total_len - target_test_size),
            )
            adaptive_N = max(min_feasible_start, min(adaptive_N, total_len - 1))
            adaptive_M = max(min_test_size, min(M, target_test_size))
            warnings.append(
                f"Adaptive WF resized windows: requested N={N}, M={M}; using N={adaptive_N}, M={adaptive_M}."
            )
            return int(adaptive_N), int(adaptive_M), int(min_train_size), True, warnings

        return N, M, min_train_size, False, warnings

    @staticmethod
    def get_wf_splits(
        total_len: int,
        N: int = 2000,
        M: int = 500,
        embargo_gap: int = 100,
        train_mode: str = "rolling",
        df: Optional[pd.DataFrame] = None,
        label_horizon: int = 100,
        min_train_size: int = 30,
        adaptive: bool = False,
        min_test_size: int = 100,
    ) -> List[WalkForwardFold]:
        """Build purged walk-forward splits.

        In adaptive mode, N/M can be shrunk for short local backtests.  The
        function never relaxes the label-horizon purge or embargo constraints.
        """
        if total_len <= 0:
            return []
        if N <= 0 or M <= 0:
            raise ValueError("N and M must be positive integers")
        if embargo_gap < 0 or label_horizon < 0:
            raise ValueError("embargo_gap and label_horizon must be non-negative")
        if train_mode not in {"expanding", "rolling"}:
            raise ValueError("train_mode must be 'expanding' or 'rolling'")

        N, M, min_train_size, was_adaptive, _warnings = WalkForwardPipeline._sanitize_sizes(
            total_len, N, M, embargo_gap, label_horizon, min_train_size, min_test_size, adaptive
        )
        if total_len <= N:
            return []

        splits: List[WalkForwardFold] = []
        fold_idx = 1

        for test_start in range(N, total_len, M):
            train_end = test_start - 1 - embargo_gap
            if train_end < 0:
                continue

            train_start = max(0, train_end - N + 1) if train_mode == "rolling" else 0

            effective_train_end = train_end - label_horizon
            effective_train_start = train_start
            effective_train_size = max(0, effective_train_end - effective_train_start + 1)
            if effective_train_size < min_train_size:
                continue

            test_end = min(test_start + M - 1, total_len - 1)
            effective_test_size = test_end - test_start + 1
            if effective_test_size < max(1, min_test_size // 2):
                continue

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
                effective_test_size=effective_test_size,
                train_mode=train_mode,
                adaptive=was_adaptive,
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
        train_mode: str = "rolling",
        df: Optional[pd.DataFrame] = None,
        adaptive: bool = False,
        min_train_size: int = 30,
        min_test_size: int = 100,
    ) -> Dict[str, Any]:
        """Generate machine-readable split diagnostics for quant validation."""
        actual_train_size = max((f.train_end - f.train_start + 1 for f in splits), default=0)
        actual_test_size = max((f.effective_test_size for f in splits), default=0)
        used_adaptive = any(getattr(f, "adaptive", False) for f in splits)
        insufficient_data = total_len <= requested_train_size
        status = "PASS" if splits else "NO_SPLITS"
        if splits and used_adaptive:
            status = "PASS_ADAPTIVE"
        report: Dict[str, Any] = {
            "status": status,
            "total_len": int(total_len),
            "requested_train_size": int(requested_train_size),
            "requested_test_size": int(test_size),
            "actual_train_size_max": int(actual_train_size),
            "actual_test_size_max": int(actual_test_size),
            "embargo_gap": int(embargo_gap),
            "label_horizon": int(label_horizon),
            "train_mode": train_mode,
            "adaptive_enabled": bool(adaptive),
            "adaptive_used": bool(used_adaptive),
            "min_train_size": int(min_train_size),
            "min_test_size": int(min_test_size),
            "fold_count": len(splits),
            "insufficient_data": bool(insufficient_data),
            "insufficient_data_for_requested_window": bool(insufficient_data),
            "minimum_required_candles": int(requested_train_size + test_size),
            "minimum_required_candles_requested": int(requested_train_size + test_size),
            "warnings": [],
            "folds": [fold.to_dict() for fold in splits],
        }
        if insufficient_data and used_adaptive:
            report["warnings"].append(
                "Requested WF train window exceeds available candles; adaptive rolling splits were used. "
                "This is valid for smoke/backtest diagnostics but less statistically strong than the full requested window."
            )
        elif insufficient_data:
            report["warnings"].append(
                "No walk-forward split was generated because total_len <= requested_train_size. "
                "Enable WF_AUTO_ADAPTIVE or use a longer dataset."
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
        train_mode: str = "rolling",
        df: Optional[pd.DataFrame] = None,
        label_horizon: int = 100,
        path: str = "data/walkforward_audit_report.json",
        min_train_size: int = 30,
        adaptive: bool = False,
        min_test_size: int = 100,
    ) -> List[WalkForwardFold]:
        splits = WalkForwardPipeline.get_wf_splits(
            total_len=total_len,
            N=N,
            M=M,
            embargo_gap=embargo_gap,
            train_mode=train_mode,
            df=df,
            label_horizon=label_horizon,
            min_train_size=min_train_size,
            adaptive=adaptive,
            min_test_size=min_test_size,
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
            adaptive=adaptive,
            min_train_size=min_train_size,
            min_test_size=min_test_size,
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
            mode = "adaptive " if getattr(fold, "adaptive", False) else ""
            print(
                f"  Fold {fold.fold_idx:02d}: |{''.join(line)}| "
                f"{mode}{fold.train_mode} train {fold.effective_train_start}->{fold.effective_train_end} | "
                f"embargo {fold.embargo_start}->{fold.embargo_end} | "
                f"test {fold.test_start}->{fold.test_end}{dates_str}"
            )

        print("\n  Legenda: [T] = Effective Train | [E] = Embargo | [V] = Out-of-Sample Test")
        print("=" * 80 + "\n")
