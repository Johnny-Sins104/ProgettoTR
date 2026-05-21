"""
Large-scale multi-asset dataset infrastructure for crypto futures ML.

This module is intentionally independent from the live/backtest engine.  Its job
is to build statistically useful, schema-consistent datasets that can later be
consumed by the ML, meta-labeling and walk-forward layers.

Design rules
------------
1. Candle data are normalized per asset before concatenation.
2. Rolling features are computed within each asset only and never use future rows.
3. Labels are generated after features, as explicit forward outcomes with a
   `label_end_time`; validation code can later purge overlapping labels.
4. No global normalization/scaling is performed here, because scalers must be fit
   inside each training window during walk-forward validation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import json
import math
import time

import numpy as np
import pandas as pd
import polars as pl

from core.market_structure_features import MarketStructureFeatureBuilder, MarketStructureConfig


DEFAULT_ASSETS: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT")
CANONICAL_COLUMNS: Tuple[str, ...] = ("datetime", "asset", "Open", "High", "Low", "Close", "Volume")


@dataclass(frozen=True)
class DatasetBuildConfig:
    """Configuration for Prompt 19 large-scale dataset generation."""

    assets: Tuple[str, ...] = DEFAULT_ASSETS
    timeframe: str = "15m"
    timeframe_minutes: int = 15
    min_years: float = 2.0
    ideal_years: float = 4.0
    output_dir: str = "data/datasets"
    label_horizon: int = 100
    atr_mult: float = 2.0
    rr_ratio: float = 2.0
    min_total_ml_samples: int = 10_000
    min_regime_samples: int = 1_000
    min_asset_years: float = 2.0
    compression: str = "snappy"
    enable_market_structure_features: bool = True
    market_structure_report_path: str = "data/datasets/market_structure_report.json"
    funding_data_path: str = ""
    open_interest_data_path: str = ""
    btc_dominance_data_path: str = ""


@dataclass
class AssetQualityReport:
    asset: str
    rows: int
    start: Optional[str]
    end: Optional[str]
    coverage_days: float
    coverage_years: float
    duplicate_timestamps_removed: int
    missing_timestamp_count: int
    null_counts: Dict[str, int]
    schema_ok: bool
    warnings: List[str] = field(default_factory=list)


@dataclass
class DatasetBuildReport:
    generated_at: str
    config: Dict[str, object]
    asset_reports: Dict[str, Dict[str, object]]
    total_candles: int
    total_features: int
    total_candidates: int
    total_meta_labels: int
    warnings: List[str]
    output_files: Dict[str, str]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _asset_to_binance_symbol(asset: str) -> str:
    cleaned = asset.replace("/", "").replace(":USDT", "").upper()
    if cleaned.endswith("USDT"):
        return cleaned
    return f"{cleaned}USDT"


def _asset_to_display_symbol(asset: str) -> str:
    cleaned = _asset_to_binance_symbol(asset)
    return cleaned.replace("USDT", "/USDT")


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


class MultiAssetDatasetBuilder:
    """Builds candle, feature, candidate-trade and meta-label datasets."""

    def __init__(self, config: Optional[DatasetBuildConfig] = None) -> None:
        self.config = config or DatasetBuildConfig()
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "feature_distribution_reports").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Input normalization and integrity
    # ------------------------------------------------------------------
    def normalize_ohlcv(self, data: object, asset: str) -> Tuple[pl.DataFrame, AssetQualityReport]:
        """
        Normalize OHLCV data from pandas/polars into the canonical schema.

        Accepted input columns are flexible: timestamp/datetime/time for time and
        either lowercase or titlecase OHLCV columns. Duplicate timestamps are
        removed deterministically. Missing 15m timestamps are reported but not
        forward-filled, because synthetic candles would pollute execution labels.
        """
        if isinstance(data, pl.DataFrame):
            df = data.clone()
        elif isinstance(data, pd.DataFrame):
            df = pl.from_pandas(data.reset_index() if data.index.name else data)
        else:
            raise TypeError(f"Unsupported OHLCV type for {asset}: {type(data)!r}")

        rename_map: Dict[str, str] = {}
        lower_to_col = {c.lower(): c for c in df.columns}
        for candidate in ("datetime", "timestamp", "time", "date"):
            if candidate in lower_to_col:
                rename_map[lower_to_col[candidate]] = "datetime"
                break
        for canonical in ("Open", "High", "Low", "Close", "Volume"):
            key = canonical.lower()
            if key in lower_to_col:
                rename_map[lower_to_col[key]] = canonical
        if rename_map:
            df = df.rename(rename_map)

        missing = [c for c in ("datetime", "Open", "High", "Low", "Close", "Volume") if c not in df.columns]
        if missing:
            raise ValueError(f"{asset}: missing required OHLCV columns: {missing}")

        df = df.select(["datetime", "Open", "High", "Low", "Close", "Volume"])
        df = self._cast_datetime_utc(df)
        df = df.with_columns([
            pl.lit(_asset_to_binance_symbol(asset)).alias("asset"),
            pl.col("Open").cast(pl.Float64),
            pl.col("High").cast(pl.Float64),
            pl.col("Low").cast(pl.Float64),
            pl.col("Close").cast(pl.Float64),
            pl.col("Volume").cast(pl.Float64),
        ]).select(list(CANONICAL_COLUMNS))

        original_rows = df.height
        df = df.sort("datetime")
        df = df.unique(subset=["datetime"], keep="first").sort("datetime")
        duplicate_removed = original_rows - df.height

        report = self._quality_report(df, _asset_to_binance_symbol(asset), duplicate_removed)
        return df, report

    def _cast_datetime_utc(self, df: pl.DataFrame) -> pl.DataFrame:
        dtype = df.schema.get("datetime")
        if dtype == pl.Utf8:
            return df.with_columns(pl.col("datetime").str.to_datetime(time_zone="UTC", strict=False))
        if dtype in (pl.Int64, pl.Int32, pl.UInt64, pl.UInt32, pl.Float64, pl.Float32):
            first = df.select(pl.col("datetime").drop_nulls().first()).item()
            unit = "ms" if first and float(first) > 1e11 else "s"
            return df.with_columns(pl.col("datetime").cast(pl.Int64).cast(pl.Datetime(unit)).dt.replace_time_zone("UTC"))
        return df.with_columns(pl.col("datetime").cast(pl.Datetime).dt.replace_time_zone("UTC"))

    def _quality_report(self, df: pl.DataFrame, asset: str, duplicate_removed: int) -> AssetQualityReport:
        null_counts = {c: int(df[c].null_count()) for c in df.columns}
        warnings: List[str] = []
        schema_ok = all(c in df.columns for c in CANONICAL_COLUMNS)
        if not schema_ok:
            warnings.append("canonical_schema_missing_columns")
        if any(v > 0 for v in null_counts.values()):
            warnings.append("null_values_present")

        missing_count = self._count_missing_timestamps(df)
        if missing_count > 0:
            warnings.append(f"missing_{self.config.timeframe}_timestamps={missing_count}")
        if duplicate_removed > 0:
            warnings.append(f"duplicates_removed={duplicate_removed}")

        start, end = None, None
        coverage_days = 0.0
        if df.height:
            start_dt = df.select(pl.col("datetime").min()).item()
            end_dt = df.select(pl.col("datetime").max()).item()
            start, end = start_dt.isoformat(), end_dt.isoformat()
            coverage_days = max((end_dt - start_dt).total_seconds() / 86400.0, 0.0)
        coverage_years = coverage_days / 365.25
        if coverage_years < self.config.min_asset_years:
            warnings.append(f"coverage_below_min_years={coverage_years:.2f}")

        return AssetQualityReport(
            asset=asset,
            rows=df.height,
            start=start,
            end=end,
            coverage_days=round(coverage_days, 2),
            coverage_years=round(coverage_years, 3),
            duplicate_timestamps_removed=duplicate_removed,
            missing_timestamp_count=missing_count,
            null_counts=null_counts,
            schema_ok=schema_ok,
            warnings=warnings,
        )

    def _count_missing_timestamps(self, df: pl.DataFrame) -> int:
        if df.height <= 1:
            return 0
        expected_ms = self.config.timeframe_minutes * 60 * 1000
        diffs = df.select(pl.col("datetime").diff().dt.total_milliseconds().alias("diff_ms")).drop_nulls()
        if diffs.is_empty():
            return 0
        gaps = diffs.filter(pl.col("diff_ms") != expected_ms)
        missing = 0
        for val in gaps["diff_ms"].to_list():
            if val and val > expected_ms:
                missing += max(int(round(val / expected_ms)) - 1, 0)
        return missing

    # ------------------------------------------------------------------
    # Feature, candidate and label generation
    # ------------------------------------------------------------------
    def build_features(self, candles: pl.DataFrame) -> pl.DataFrame:
        """Generate causal rolling features per asset only."""
        if candles.is_empty():
            return candles
        frames = []
        for asset in candles["asset"].unique().to_list():
            asset_df = candles.filter(pl.col("asset") == asset).sort("datetime")
            pd_df = asset_df.to_pandas()
            pd_df["return_1"] = pd_df["Close"].pct_change()
            pd_df["log_return_1"] = np.log(pd_df["Close"] / pd_df["Close"].shift(1))
            pd_df["hl_range_pct"] = (pd_df["High"] - pd_df["Low"]) / pd_df["Close"].replace(0, np.nan)
            pd_df["rolling_vol_96"] = pd_df["log_return_1"].rolling(96, min_periods=20).std()
            pd_df["rolling_vol_288"] = pd_df["log_return_1"].rolling(288, min_periods=50).std()
            pd_df["realized_vol_1d"] = pd_df["log_return_1"].rolling(96, min_periods=20).std() * np.sqrt(96)
            pd_df["volume_ratio_96"] = pd_df["Volume"] / pd_df["Volume"].rolling(96, min_periods=20).mean()
            ema_fast = pd_df["Close"].ewm(span=48, adjust=False, min_periods=20).mean()
            ema_slow = pd_df["Close"].ewm(span=192, adjust=False, min_periods=50).mean()
            pd_df["ema_fast"] = ema_fast
            pd_df["ema_slow"] = ema_slow
            pd_df["ema_slope_48"] = ema_fast.pct_change(12)
            pd_df["trend_strength"] = (ema_fast - ema_slow) / pd_df["Close"].replace(0, np.nan)
            pd_df["atr_proxy_pct"] = pd_df["hl_range_pct"].rolling(96, min_periods=20).mean()
            pd_df["momentum_4h"] = pd_df["Close"].pct_change(16)
            pd_df["momentum_1d"] = pd_df["Close"].pct_change(96)
            pd_df["volatility_regime"] = self._volatility_regime(pd_df["rolling_vol_96"])
            pd_df["market_regime"] = self._market_regime(pd_df["trend_strength"], pd_df["rolling_vol_96"])
            pd_df["regime_confidence"] = self._regime_confidence(pd_df["trend_strength"], pd_df["rolling_vol_96"])
            frames.append(pl.from_pandas(pd_df))
        features = pl.concat(frames, how="diagonal_relaxed").sort(["asset", "datetime"])
        if self.config.enable_market_structure_features:
            external_sources = {}
            if self.config.funding_data_path:
                external_sources["funding"] = self.config.funding_data_path
            if self.config.open_interest_data_path:
                external_sources["open_interest"] = self.config.open_interest_data_path
            if self.config.btc_dominance_data_path:
                external_sources["btc_dominance"] = self.config.btc_dominance_data_path
            features, _ = MarketStructureFeatureBuilder(
                MarketStructureConfig(
                    timeframe_minutes=self.config.timeframe_minutes,
                    output_report_path=self.config.market_structure_report_path,
                )
            ).enrich(features, external_sources=external_sources or None, write_report=True)
        return features

    def _volatility_regime(self, vol: pd.Series) -> pd.Series:
        out = pd.Series("UNKNOWN", index=vol.index, dtype="object")
        valid = vol.dropna()
        if valid.empty:
            return out
        q33, q66, q90 = valid.quantile([0.33, 0.66, 0.90])
        out.loc[vol <= q33] = "LOW_VOL"
        out.loc[(vol > q33) & (vol <= q66)] = "NORMAL"
        out.loc[(vol > q66) & (vol <= q90)] = "HIGH_VOL"
        out.loc[vol > q90] = "EXTREME"
        return out

    def _market_regime(self, trend: pd.Series, vol: pd.Series) -> pd.Series:
        out = pd.Series("UNKNOWN", index=trend.index, dtype="object")
        abs_trend = trend.abs()
        valid = abs_trend.dropna()
        if valid.empty:
            return out
        trend_q70 = valid.quantile(0.70)
        trend_q40 = valid.quantile(0.40)
        out.loc[abs_trend >= trend_q70] = "TRENDING"
        out.loc[abs_trend <= trend_q40] = "RANGING"
        out.loc[(abs_trend > trend_q40) & (abs_trend < trend_q70)] = "TRANSITIONAL"
        out.loc[vol.isna()] = "UNKNOWN"
        return out

    def _regime_confidence(self, trend: pd.Series, vol: pd.Series) -> pd.Series:
        abs_trend = trend.abs()
        denom = abs_trend.rolling(288, min_periods=50).quantile(0.90).replace(0, np.nan)
        conf = (abs_trend / denom).clip(lower=0, upper=1).fillna(0.0)
        return conf

    def build_candidate_trades(self, features: pl.DataFrame) -> pl.DataFrame:
        """Generate candidate setups without forward labels."""
        if features.is_empty():
            return features
        df = features.to_pandas()
        df["candidate_side"] = "NONE"
        df.loc[(df["momentum_4h"] > 0) & (df["trend_strength"] > 0) & (df["volume_ratio_96"] > 0.8), "candidate_side"] = "BUY"
        df.loc[(df["momentum_4h"] < 0) & (df["trend_strength"] < 0) & (df["volume_ratio_96"] > 0.8), "candidate_side"] = "SELL"
        df["setup_quality"] = (
            40 * df["regime_confidence"].fillna(0)
            + 30 * df["volume_ratio_96"].replace([np.inf, -np.inf], np.nan).fillna(1).clip(0, 2) / 2
            + 30 * df["rolling_vol_96"].rank(pct=True).fillna(0)
        ).clip(0, 100)
        candidates = df[df["candidate_side"] != "NONE"].copy()
        keep = [
            "datetime", "asset", "candidate_side", "Close", "High", "Low", "Volume",
            "return_1", "rolling_vol_96", "rolling_vol_288", "realized_vol_1d",
            "volume_ratio_96", "ema_slope_48", "trend_strength", "atr_proxy_pct",
            "momentum_4h", "momentum_1d", "volatility_regime", "market_regime",
            "regime_confidence", "setup_quality",
            "realized_vol_1d_ms", "realized_vol_1w_ms", "volatility_compression",
            "is_vol_compressed", "is_vol_expanding", "htf_1h_return",
            "htf_4h_return", "htf_1h_trend", "htf_4h_trend",
            "htf_trend_alignment", "session_asia", "session_london", "session_ny",
            "session_overlap_london_ny", "day_of_week", "sweep_high", "sweep_low",
            "liquidity_sweep_score", "volume_z_1d", "range_z_1d",
            "funding_rate", "funding_rate_z", "funding_available",
            "open_interest", "open_interest_change_1d", "open_interest_available",
            "btc_dominance", "btc_dominance_change_1d", "btc_dominance_available",
            "btc_return_1", "btc_realized_vol_1d", "btc_htf_4h_trend",
            "asset_vs_btc_return_1",
        ]
        return pl.from_pandas(candidates[keep]).sort(["asset", "datetime"])

    def build_meta_labels(self, candles: pl.DataFrame, candidates: pl.DataFrame) -> pl.DataFrame:
        """Generate meta-labels using forward OHLCV only as labels, not features."""
        if candidates.is_empty():
            return candidates
        candle_pd = {asset: df.sort_values("datetime").reset_index(drop=True) for asset, df in candles.to_pandas().groupby("asset")}
        rows: List[Dict[str, object]] = []
        for row in candidates.to_dicts():
            asset = str(row["asset"])
            df = candle_pd.get(asset)
            if df is None or df.empty:
                continue
            ts = pd.Timestamp(row["datetime"])
            # Timestamp is exact because candidates are derived from candles.
            matches = df.index[df["datetime"] == ts].tolist()
            if not matches:
                continue
            idx = int(matches[0])
            label = self._label_trade(df, idx, str(row["candidate_side"]))
            if label is None:
                continue
            label_end_idx = min(idx + self.config.label_horizon, len(df) - 1)
            out = dict(row)
            out.update(label)
            out["label_horizon"] = self.config.label_horizon
            out["label_end_time"] = df.loc[label_end_idx, "datetime"]
            rows.append(out)
        return pl.from_dicts(rows) if rows else pl.DataFrame()

    def _label_trade(self, df: pd.DataFrame, idx: int, side: str) -> Optional[Dict[str, object]]:
        if idx >= len(df) - 2:
            return None
        entry = _safe_float(df.loc[idx, "Close"])
        atr = _safe_float(df.loc[idx, "atr_proxy_pct"], 0.0) * entry
        if atr <= 0:
            atr = max(_safe_float(df.loc[idx, "High"]) - _safe_float(df.loc[idx, "Low"]), entry * 0.002)
        if side == "BUY":
            sl = entry - self.config.atr_mult * atr
            tp = entry + self.config.atr_mult * atr * self.config.rr_ratio
        else:
            sl = entry + self.config.atr_mult * atr
            tp = entry - self.config.atr_mult * atr * self.config.rr_ratio

        max_forward = min(self.config.label_horizon, len(df) - idx - 1)
        for offset in range(1, max_forward + 1):
            high = _safe_float(df.loc[idx + offset, "High"])
            low = _safe_float(df.loc[idx + offset, "Low"])
            if side == "BUY":
                hit_sl = low <= sl
                hit_tp = high >= tp
            else:
                hit_sl = high >= sl
                hit_tp = low <= tp
            if hit_sl and hit_tp:
                return {"outcome": 0, "label_reason": "sl_and_tp_same_bar", "gross_rr": -1.0}
            if hit_tp:
                return {"outcome": 1, "label_reason": "tp", "gross_rr": self.config.rr_ratio}
            if hit_sl:
                return {"outcome": 0, "label_reason": "sl", "gross_rr": -1.0}
        return {"outcome": 0, "label_reason": "timeout", "gross_rr": 0.0}

    # ------------------------------------------------------------------
    # Build orchestration and reports
    # ------------------------------------------------------------------
    def build_from_frames(self, frames: Mapping[str, object]) -> DatasetBuildReport:
        asset_reports: Dict[str, AssetQualityReport] = {}
        candles_by_asset: List[pl.DataFrame] = []
        warnings: List[str] = []
        for asset, data in frames.items():
            normalized, report = self.normalize_ohlcv(data, asset)
            asset_reports[report.asset] = report
            warnings.extend([f"{report.asset}: {w}" for w in report.warnings])
            if not normalized.is_empty():
                candles_by_asset.append(normalized)

        if not candles_by_asset:
            raise ValueError("No valid asset candle frames were provided.")

        candles = pl.concat(candles_by_asset, how="vertical_relaxed").sort(["asset", "datetime"])
        features = self.build_features(candles)
        candidates = self.build_candidate_trades(features)
        meta_labels = self.build_meta_labels(features.select([c for c in features.columns if c in set(CANONICAL_COLUMNS) | {"atr_proxy_pct"}]), candidates)

        output_files = self._write_outputs(candles, features, candidates, meta_labels)
        report = self._write_reports(asset_reports, candles, features, candidates, meta_labels, warnings, output_files)
        return report

    def build_from_parquet_paths(self, paths: Mapping[str, str]) -> DatasetBuildReport:
        frames: Dict[str, pl.DataFrame] = {}
        for asset, path in paths.items():
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"{asset}: parquet path not found: {p}")
            frames[asset] = pl.read_parquet(p)
        return self.build_from_frames(frames)

    def _write_outputs(self, candles: pl.DataFrame, features: pl.DataFrame, candidates: pl.DataFrame, meta_labels: pl.DataFrame) -> Dict[str, str]:
        outputs = {
            "candles": self.output_dir / "candles_multi_asset.parquet",
            "market_features": self.output_dir / "market_features.parquet",
            "candidate_trades": self.output_dir / "candidate_trades.parquet",
            "meta_label_dataset": self.output_dir / "meta_label_dataset.parquet",
            "regime_tagged_dataset": self.output_dir / "regime_tagged_dataset.parquet",
        }
        candles.write_parquet(outputs["candles"], compression=self.config.compression)
        features.write_parquet(outputs["market_features"], compression=self.config.compression)
        candidates.write_parquet(outputs["candidate_trades"], compression=self.config.compression)
        meta_labels.write_parquet(outputs["meta_label_dataset"], compression=self.config.compression)
        features.write_parquet(outputs["regime_tagged_dataset"], compression=self.config.compression)
        return {k: str(v) for k, v in outputs.items()}

    def _write_reports(
        self,
        asset_reports: Mapping[str, AssetQualityReport],
        candles: pl.DataFrame,
        features: pl.DataFrame,
        candidates: pl.DataFrame,
        meta_labels: pl.DataFrame,
        warnings: List[str],
        output_files: Mapping[str, str],
    ) -> DatasetBuildReport:
        if meta_labels.height < self.config.min_total_ml_samples:
            warnings.append(f"total_ml_samples_below_minimum={meta_labels.height}<{self.config.min_total_ml_samples}")

        regime_balance = self._regime_balance_report(meta_labels if not meta_labels.is_empty() else features)
        for regime, count in regime_balance.get("market_regime_counts", {}).items():
            if regime != "UNKNOWN" and count < self.config.min_regime_samples:
                warnings.append(f"regime_{regime}_below_minimum={count}<{self.config.min_regime_samples}")

        feature_integrity = self._feature_integrity_report(features)
        feature_distribution = self._feature_distribution_report(features)
        asset_coverage = {asset: asdict(report) for asset, report in asset_reports.items()}

        self._write_json("asset_coverage_report.json", asset_coverage)
        self._write_json("regime_balance_report.json", regime_balance)
        self._write_json("feature_integrity_report.json", feature_integrity)
        self._write_json("feature_distribution_reports/feature_distribution_summary.json", feature_distribution)

        report = DatasetBuildReport(
            generated_at=_utc_now_iso(),
            config=asdict(self.config),
            asset_reports=asset_coverage,
            total_candles=candles.height,
            total_features=features.height,
            total_candidates=candidates.height,
            total_meta_labels=meta_labels.height,
            warnings=warnings,
            output_files=dict(output_files),
        )
        self._write_json("dataset_summary.json", asdict(report))
        print(f"[DatasetBuilder] Summary exported -> {self.output_dir / 'dataset_summary.json'}")
        print(f"[DatasetBuilder] Meta-label samples: {meta_labels.height} | Candidates: {candidates.height} | Candles: {candles.height}")
        return report

    def _regime_balance_report(self, df: pl.DataFrame) -> Dict[str, object]:
        if df.is_empty():
            return {"market_regime_counts": {}, "volatility_regime_counts": {}, "asset_counts": {}}
        return {
            "market_regime_counts": self._value_counts(df, "market_regime"),
            "volatility_regime_counts": self._value_counts(df, "volatility_regime"),
            "asset_counts": self._value_counts(df, "asset"),
        }

    def _value_counts(self, df: pl.DataFrame, col: str) -> Dict[str, int]:
        if col not in df.columns:
            return {}
        counts = df.group_by(col).len().sort("len", descending=True).to_dicts()
        return {str(row[col]): int(row["len"]) for row in counts}

    def _feature_integrity_report(self, features: pl.DataFrame) -> Dict[str, object]:
        numeric_cols = [c for c, dtype in features.schema.items() if dtype.is_numeric()]
        nan_counts = {}
        null_counts = {}
        inf_counts = {}
        for col in numeric_cols:
            series = features[col]
            null_counts[col] = int(series.null_count())
            nan_counts[col] = int(series.is_nan().sum()) if series.dtype.is_float() else 0
            inf_counts[col] = int(np.isinf(series.to_numpy()).sum()) if series.dtype.is_float() else 0
        return {
            "rows": features.height,
            "numeric_columns": numeric_cols,
            "null_counts": null_counts,
            "nan_counts": nan_counts,
            "inf_counts": inf_counts,
            "causality_note": "Rolling features are computed per asset with pandas rolling/ewm using current and past rows only. No global scaler is fit here.",
        }

    def _feature_distribution_report(self, features: pl.DataFrame) -> Dict[str, object]:
        numeric_cols = [c for c, dtype in features.schema.items() if dtype.is_numeric()]
        report: Dict[str, object] = {}
        for col in numeric_cols:
            s = features[col].drop_nulls()
            if s.is_empty():
                continue
            report[col] = {
                "min": float(s.min()),
                "p05": float(s.quantile(0.05)),
                "median": float(s.median()),
                "p95": float(s.quantile(0.95)),
                "max": float(s.max()),
            }
        return report

    def _write_json(self, relative_path: str, payload: object) -> None:
        path = self.output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)


class BinanceFuturesHistoricalDownloader:
    """Optional CCXT downloader for Binance USDT-M futures OHLCV."""

    def __init__(self, timeframe: str = "15m", rate_limit_seconds: float = 0.25) -> None:
        self.timeframe = timeframe
        self.rate_limit_seconds = rate_limit_seconds

    async def fetch_asset(self, asset: str, years: float = 2.0, limit: int = 1000) -> pd.DataFrame:
        try:
            import ccxt.async_support as ccxt_async  # type: ignore
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("ccxt is required for live downloading. Install requirements first.") from exc

        exchange = ccxt_async.binanceusdm({"enableRateLimit": True})
        symbol = _asset_to_display_symbol(asset)
        candle_ms = 15 * 60 * 1000
        target_candles = int(years * 365.25 * 24 * 4)
        since = int(time.time() * 1000) - target_candles * candle_ms
        rows: List[List[float]] = []
        try:
            while len(rows) < target_candles:
                batch = await exchange.fetch_ohlcv(symbol, timeframe=self.timeframe, since=since, limit=limit)
                if not batch:
                    break
                if rows and batch[0][0] <= rows[-1][0]:
                    since = rows[-1][0] + candle_ms
                    continue
                rows.extend(batch)
                since = batch[-1][0] + candle_ms
                await asyncio_sleep(self.rate_limit_seconds)
        finally:
            await exchange.close()

        rows = rows[-target_candles:]
        df = pd.DataFrame(rows, columns=["datetime", "Open", "High", "Low", "Close", "Volume"])
        df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
        return df


async def asyncio_sleep(seconds: float) -> None:  # isolated for test patching
    import asyncio
    await asyncio.sleep(seconds)
