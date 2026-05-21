"""
core/training_dataset_loader.py — Multi-asset training dataset adapter
=====================================================================

Connects the Prompt 19 multi-asset parquet datasets to the legacy
MetaLabelingEngine / RegimeModelManager training interface.

The model still expects the historical FEATURE_NAMES schema used by live
inference.  This adapter maps the expanded multi-asset meta-label dataset into
that canonical schema while preserving diagnostics about asset and regime
balance.  It deliberately does not fit scalers or global normalizers, so it does
not introduce future-derived normalization leakage.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import Config
from core.regime_model_manager import FEATURE_NAMES


@dataclass
class TrainingDatasetReport:
    source_path: str
    output_path: str
    total_rows_loaded: int
    rows_after_cleaning: int
    dropped_rows: int
    nan_rows_removed: int
    duplicate_asset_timestamp_rows: int
    per_asset_counts: Dict[str, int]
    per_regime_counts: Dict[str, int]
    per_volatility_regime_counts: Dict[str, int]
    outcome_counts: Dict[str, int]
    feature_columns: List[str]
    warnings: List[str]
    leakage_note: str


class MultiAssetTrainingDatasetLoader:
    """Loads expanded parquet meta-label data and adapts it for XGBoost training."""

    DEFAULT_SOURCE = os.path.join("data", "datasets", "meta_label_dataset.parquet")
    DEFAULT_OUTPUT = os.path.join("data", "market_features.parquet")
    DEFAULT_REPORT = os.path.join("data", "training_dataset_report.json")
    DEFAULT_ASSET_REPORT = os.path.join("data", "asset_training_balance_report.json")
    DEFAULT_SPLIT_REPORT = os.path.join("data", "training_split_report.json")
    DEFAULT_MACRO_REPORT = os.path.join("data", "macro_feature_training_report.json")

    @classmethod
    def expanded_dataset_exists(cls, path: Optional[str] = None) -> bool:
        return os.path.exists(path or getattr(Config, "AI_EXPANDED_DATASET_PATH", cls.DEFAULT_SOURCE))

    @classmethod
    def load_expanded_training_dataset(
        cls,
        source_path: Optional[str] = None,
        output_path: Optional[str] = None,
        report_path: Optional[str] = None,
        min_samples: Optional[int] = None,
        write_compatible_parquet: bool = True,
    ) -> Tuple[pd.DataFrame, TrainingDatasetReport]:
        """Load expanded data and return the canonical legacy training frame.

        The returned DataFrame contains exactly FEATURE_NAMES + outcome so it can
        be passed to MetaLabelingEngine.train(features_df=...).
        """
        source = source_path or getattr(Config, "AI_EXPANDED_DATASET_PATH", cls.DEFAULT_SOURCE)
        output = output_path or getattr(Config, "AI_FEATURES_PATH", cls.DEFAULT_OUTPUT)
        report = report_path or cls.DEFAULT_REPORT
        min_samples = int(min_samples or getattr(Config, "AI_EXPANDED_MIN_SAMPLES", 10_000))

        if not os.path.exists(source):
            raise FileNotFoundError(f"Expanded training dataset not found: {source}")

        raw = cls._read_parquet(source)
        total_rows = len(raw)
        duplicate_rows = cls._count_duplicate_asset_timestamps(raw)

        adapted = cls._adapt_to_legacy_schema(raw)
        before_clean = len(adapted)
        adapted = adapted.replace([np.inf, -np.inf], np.nan)
        adapted = adapted.dropna(subset=FEATURE_NAMES + ["outcome"])
        nan_removed = before_clean - len(adapted)

        adapted["outcome"] = adapted["outcome"].astype(int).clip(0, 1)
        for col in FEATURE_NAMES:
            adapted[col] = pd.to_numeric(adapted[col], errors="coerce").fillna(0.0).astype(float)

        warnings: List[str] = []
        if len(adapted) < min_samples:
            warnings.append(f"expanded_training_samples_below_minimum={len(adapted)}<{min_samples}")
        if duplicate_rows > 0:
            warnings.append(f"duplicate_asset_timestamps_detected={duplicate_rows}")

        per_asset_counts = cls._value_counts(raw, "asset")
        per_regime_counts = cls._value_counts(raw, "market_regime")
        per_vol_counts = cls._value_counts(raw, "volatility_regime")
        outcome_counts = {str(k): int(v) for k, v in adapted["outcome"].value_counts().sort_index().to_dict().items()}

        for regime, count in per_regime_counts.items():
            if regime not in ("UNKNOWN", "TRANSITIONAL") and count < getattr(Config, "AI_MIN_REGIME_SAMPLES", 1_000):
                warnings.append(f"regime_{regime}_below_minimum={count}<{getattr(Config, 'AI_MIN_REGIME_SAMPLES', 1000)}")

        final_df = adapted[FEATURE_NAMES + ["outcome"]].reset_index(drop=True)

        if write_compatible_parquet:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            try:
                import polars as pl
                pl.from_pandas(final_df).write_parquet(output, compression="snappy")
            except Exception:
                final_df.to_parquet(output, index=False)

        payload = TrainingDatasetReport(
            source_path=source,
            output_path=output,
            total_rows_loaded=total_rows,
            rows_after_cleaning=len(final_df),
            dropped_rows=total_rows - len(final_df),
            nan_rows_removed=nan_removed,
            duplicate_asset_timestamp_rows=duplicate_rows,
            per_asset_counts=per_asset_counts,
            per_regime_counts=per_regime_counts,
            per_volatility_regime_counts=per_vol_counts,
            outcome_counts=outcome_counts,
            feature_columns=list(FEATURE_NAMES),
            warnings=warnings,
            leakage_note=(
                "Expanded labels are loaded from meta_label_dataset.parquet; features are adapted "
                "row-wise without fitting global scalers or using future-derived normalization. "
                "Walk-forward/purging remains the validation layer responsibility."
            ),
        )
        cls._write_reports(payload, report)
        cls._write_macro_feature_report(raw, cls.DEFAULT_MACRO_REPORT)
        return final_df, payload

    @staticmethod
    def _read_parquet(path: str) -> pd.DataFrame:
        try:
            import polars as pl
            return pl.read_parquet(path).to_pandas()
        except Exception:
            return pd.read_parquet(path)

    @staticmethod
    def _count_duplicate_asset_timestamps(df: pd.DataFrame) -> int:
        if "asset" in df.columns and "datetime" in df.columns:
            return int(df.duplicated(subset=["asset", "datetime"]).sum())
        return 0

    @staticmethod
    def _value_counts(df: pd.DataFrame, col: str) -> Dict[str, int]:
        if col not in df.columns:
            return {}
        return {str(k): int(v) for k, v in df[col].fillna("UNKNOWN").value_counts().to_dict().items()}

    @classmethod
    def _adapt_to_legacy_schema(cls, raw: pd.DataFrame) -> pd.DataFrame:
        df = raw.copy()

        close = cls._series(df, "Close", 1.0).replace(0, np.nan)
        momentum_4h = cls._series(df, "momentum_4h", 0.0)
        momentum_1d = cls._series(df, "momentum_1d", 0.0)
        trend_strength = cls._series(df, "trend_strength", 0.0)
        volume_ratio = cls._series(df, "volume_ratio_96", 1.0).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        atr_proxy_pct = cls._series(df, "atr_proxy_pct", 0.0).abs().fillna(0.0)
        ema_slope = cls._series(df, "ema_slope_48", 0.0).fillna(0.0)
        regime_conf = cls._series(df, "regime_confidence", 0.0).fillna(0.0)
        setup_quality = cls._series(df, "setup_quality", 50.0).fillna(50.0)
        htf_alignment = cls._series(df, "htf_trend_alignment", 0.0).fillna(0.0)
        sweep_score = cls._series(df, "liquidity_sweep_score", 0.0).fillna(0.0)
        vol_compression = cls._series(df, "volatility_compression", 1.0).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        btc_beta = cls._series(df, "asset_vs_btc_return_1", 0.0).fillna(0.0)
        funding_z = cls._series(df, "funding_rate_z", 0.0).fillna(0.0)
        oi_change = cls._series(df, "open_interest_change_1d", 0.0).fillna(0.0)
        dominance_change = cls._series(df, "btc_dominance_change_1d", 0.0).fillna(0.0)

        # Legacy feature approximations from causal multi-asset features.
        # These are deterministic row-wise transforms and do not fit on the full dataset.
        out = pd.DataFrame(index=df.index)
        out["rsi"] = (50.0 + momentum_4h.fillna(0.0) * 500.0).clip(0, 100)
        out["adx"] = (regime_conf * 100.0).clip(0, 100)
        out["atr_pct"] = (0.70 * atr_proxy_pct + 0.30 * cls._series(df, "realized_vol_1d_ms", 0.0).abs()).clip(0, 1)
        out["ema_slope"] = (0.70 * ema_slope + 0.30 * cls._series(df, "htf_4h_return", 0.0)).clip(-1, 1)
        out["close_vs_ema"] = (0.75 * trend_strength + 0.25 * cls._series(df, "htf_1h_return", 0.0)).clip(-1, 1)
        out["dist_to_psy"] = (cls._distance_to_psychological_level(close).fillna(0.0) + sweep_score.clip(0, 0.02) * 10.0).clip(0, 1)
        out["volume_ratio"] = (volume_ratio + oi_change.abs().clip(0, 1)).clip(0, 10)
        out["bb_position"] = (0.5 + momentum_1d.fillna(0.0) * 10.0 + btc_beta * 5.0 - dominance_change * 2.0).clip(0, 1)
        out["engulfing"] = df.get("candidate_side", pd.Series("NONE", index=df.index)).map({"BUY": 1.0, "SELL": -1.0}).fillna(0.0)
        out["regime"] = df.get("market_regime", pd.Series("RANGING", index=df.index)).astype(str).str.upper().map({"TRENDING": 1.0}).fillna(0.0)
        out["in_fvg"] = (sweep_score > 0).astype(float)
        out["near_sr"] = htf_alignment.clip(0, 1)
        out["volume_bias_enc"] = np.sign(volume_ratio.fillna(1.0) - 1.0)
        out["setup_quality"] = (setup_quality + 8.0 * htf_alignment + 4.0 * (vol_compression < 0.75).astype(float) - 3.0 * funding_z.abs().clip(0, 3)).clip(0, 100)
        out["outcome"] = pd.to_numeric(df.get("outcome", 0), errors="coerce").fillna(0).astype(int).clip(0, 1)

        # Symmetry transform for sell candidates, matching legacy DataCollector behavior.
        side = df.get("candidate_side", pd.Series("BUY", index=df.index)).astype(str).str.upper()
        sell_mask = side == "SELL"
        for col in ["engulfing", "close_vs_ema", "ema_slope", "near_sr", "volume_bias_enc"]:
            out.loc[sell_mask, col] = -out.loc[sell_mask, col]

        return out

    @staticmethod
    def _series(df: pd.DataFrame, col: str, default: float) -> pd.Series:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").astype(float)
        return pd.Series(default, index=df.index, dtype=float)

    @staticmethod
    def _distance_to_psychological_level(close: pd.Series) -> pd.Series:
        # Distance to nearest 100-dollar level as a fraction of price.  It is a
        # local row-wise transform, not a fitted scaler.
        level = 100.0
        remainder = close % level
        dist = np.minimum(remainder, level - remainder) / close.replace(0, np.nan)
        return pd.Series(dist, index=close.index).clip(0, 1)

    @classmethod
    def _write_reports(cls, report: TrainingDatasetReport, report_path: str) -> None:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        # Smaller, focused reports used by the prompt/test checklist.
        asset_path = Path(cls.DEFAULT_ASSET_REPORT)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        with asset_path.open("w", encoding="utf-8") as f:
            json.dump({"per_asset_counts": report.per_asset_counts}, f, indent=2)

        split_path = Path(cls.DEFAULT_SPLIT_REPORT)
        with split_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_path": report.source_path,
                    "rows_after_cleaning": report.rows_after_cleaning,
                    "note": "This loader prepares the full expanded training set. Purged walk-forward split auditing is handled by core.walk_forward.",
                },
                f,
                indent=2,
            )

    @staticmethod
    def _write_macro_feature_report(raw: pd.DataFrame, path: str) -> None:
        macro_cols = [
            "realized_vol_1d_ms", "realized_vol_1w_ms", "volatility_compression",
            "htf_1h_return", "htf_4h_return", "htf_trend_alignment",
            "session_asia", "session_london", "session_ny", "liquidity_sweep_score",
            "funding_rate", "funding_available", "open_interest", "open_interest_available",
            "btc_dominance", "btc_dominance_available", "btc_return_1", "asset_vs_btc_return_1",
        ]
        present = [c for c in macro_cols if c in raw.columns]
        payload = {
            "present_macro_feature_count": len(present),
            "present_macro_features": present,
            "missing_macro_features": [c for c in macro_cols if c not in raw.columns],
            "availability": {},
            "note": "Macro and market-structure features are generated causally and mapped into the legacy FEATURE_NAMES adapter without global fitting.",
        }
        for col in ("funding_available", "open_interest_available", "btc_dominance_available"):
            if col in raw.columns:
                payload["availability"][col] = float(pd.to_numeric(raw[col], errors="coerce").fillna(0).mean())
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

