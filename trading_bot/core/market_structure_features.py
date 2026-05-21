"""
Market structure and macro-context features for crypto futures ML.

Prompt 26 scope
---------------
This module adds *causal* contextual features to the multi-asset dataset
pipeline.  It is deliberately offline-first: funding, open interest and BTC
Dominance can be merged from local parquet/CSV sources when available, while
safe proxy features are generated from OHLCV alone when external data are not
provided.

Design rules
------------
1. All rolling features are grouped by asset and use only current/past bars.
2. Higher-timeframe context uses rolling/resampled values known at the current
   15m candle; no forward-filled future bar close is used.
3. External macro data are joined with backward as-of semantics, never nearest
   or forward-looking joins.
4. Missing external macro sources are represented by explicit availability flags
   and neutral numeric defaults so the training pipeline remains reproducible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple
import json
import math

import numpy as np
import pandas as pd
import polars as pl


@dataclass(frozen=True)
class MarketStructureConfig:
    timeframe_minutes: int = 15
    session_timezone: str = "UTC"
    output_report_path: str = "data/datasets/market_structure_report.json"
    btc_asset: str = "BTCUSDT"
    htf_1h_window: int = 4          # 4 x 15m
    htf_4h_window: int = 16         # 16 x 15m
    compression_window: int = 96    # 1 day
    sweep_window: int = 20
    realized_vol_short: int = 96    # 1 day
    realized_vol_long: int = 672    # 1 week


@dataclass
class MarketStructureReport:
    rows: int
    assets: Dict[str, int]
    feature_columns: Dict[str, str]
    external_sources: Dict[str, bool]
    null_counts: Dict[str, int]
    warnings: list[str]


class MarketStructureFeatureBuilder:
    """Causal market-structure feature generator."""

    FUNDING_COLUMNS = ("funding_rate", "funding_rate_z", "funding_available")
    OPEN_INTEREST_COLUMNS = ("open_interest", "open_interest_change_1d", "open_interest_available")
    BTC_DOMINANCE_COLUMNS = ("btc_dominance", "btc_dominance_change_1d", "btc_dominance_available")

    def __init__(self, config: Optional[MarketStructureConfig] = None) -> None:
        self.config = config or MarketStructureConfig()

    def enrich(
        self,
        features: pl.DataFrame,
        external_sources: Optional[Mapping[str, object]] = None,
        write_report: bool = False,
    ) -> Tuple[pl.DataFrame, MarketStructureReport]:
        """Return feature frame enriched with causal macro/context features."""
        if features.is_empty():
            report = MarketStructureReport(0, {}, {}, {}, {}, ["empty_input"])
            return features, report

        df = features.to_pandas().copy()
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df["asset"] = df["asset"].astype(str).str.upper()
        df = df.sort_values(["asset", "datetime"]).reset_index(drop=True)

        frames = []
        for asset, g in df.groupby("asset", sort=False):
            frames.append(self._enrich_asset(g.copy()))
        out = pd.concat(frames, ignore_index=True).sort_values(["asset", "datetime"]).reset_index(drop=True)

        source_flags = {"funding": False, "open_interest": False, "btc_dominance": False}
        if external_sources:
            if "funding" in external_sources and external_sources["funding"] is not None:
                out = self._merge_asset_asof(out, self._load_external(external_sources["funding"]), self.FUNDING_COLUMNS)
                source_flags["funding"] = True
            if "open_interest" in external_sources and external_sources["open_interest"] is not None:
                out = self._merge_asset_asof(out, self._load_external(external_sources["open_interest"]), self.OPEN_INTEREST_COLUMNS)
                source_flags["open_interest"] = True
            if "btc_dominance" in external_sources and external_sources["btc_dominance"] is not None:
                out = self._merge_global_asof(out, self._load_external(external_sources["btc_dominance"]), self.BTC_DOMINANCE_COLUMNS)
                source_flags["btc_dominance"] = True

        out = self._ensure_external_defaults(out)
        out = self._add_cross_asset_context(out)
        out = self._sanitize(out)

        enriched = pl.from_pandas(out)
        report = self.build_report(enriched, source_flags)
        if write_report:
            self.write_report(report)
        return enriched, report

    def _enrich_asset(self, g: pd.DataFrame) -> pd.DataFrame:
        close = pd.to_numeric(g["Close"], errors="coerce")
        high = pd.to_numeric(g["High"], errors="coerce")
        low = pd.to_numeric(g["Low"], errors="coerce")
        volume = pd.to_numeric(g["Volume"], errors="coerce")
        log_ret = np.log(close / close.shift(1))

        # Realized volatility and volatility compression/expansion.
        g["realized_vol_1d_ms"] = log_ret.rolling(self.config.realized_vol_short, min_periods=20).std() * math.sqrt(self.config.realized_vol_short)
        g["realized_vol_1w_ms"] = log_ret.rolling(self.config.realized_vol_long, min_periods=100).std() * math.sqrt(self.config.realized_vol_long)
        vol_med = g["realized_vol_1d_ms"].rolling(self.config.compression_window, min_periods=20).median()
        g["volatility_compression"] = (g["realized_vol_1d_ms"] / vol_med.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        g["is_vol_compressed"] = (g["volatility_compression"] < 0.75).astype(float)
        g["is_vol_expanding"] = (g["volatility_compression"] > 1.25).astype(float)

        # HTF context from causal rolling windows. These are proxies for 1H/4H
        # trend state without requiring resample alignment ambiguity.
        g["htf_1h_return"] = close.pct_change(self.config.htf_1h_window)
        g["htf_4h_return"] = close.pct_change(self.config.htf_4h_window)
        g["htf_1h_trend"] = np.sign(g["htf_1h_return"].fillna(0.0))
        g["htf_4h_trend"] = np.sign(g["htf_4h_return"].fillna(0.0))
        g["htf_trend_alignment"] = (g["htf_1h_trend"] == g["htf_4h_trend"]).astype(float)
        g.loc[(g["htf_1h_trend"] == 0) | (g["htf_4h_trend"] == 0), "htf_trend_alignment"] = 0.0

        # Session regime in UTC: Asia 00-07, London 08-15, NY 13-21.
        hour = g["datetime"].dt.hour
        g["session_asia"] = ((hour >= 0) & (hour < 8)).astype(float)
        g["session_london"] = ((hour >= 8) & (hour < 16)).astype(float)
        g["session_ny"] = ((hour >= 13) & (hour < 22)).astype(float)
        g["session_overlap_london_ny"] = ((hour >= 13) & (hour < 16)).astype(float)
        g["day_of_week"] = g["datetime"].dt.dayofweek.astype(float)

        # Liquidity sweep proxies: current candle breaches a rolling prior high/low
        # and closes back inside the range. Shift(1) keeps the prior range causal.
        prior_high = high.rolling(self.config.sweep_window, min_periods=5).max().shift(1)
        prior_low = low.rolling(self.config.sweep_window, min_periods=5).min().shift(1)
        candle_range = (high - low).replace(0, np.nan)
        g["sweep_high"] = ((high > prior_high) & (close < prior_high)).astype(float)
        g["sweep_low"] = ((low < prior_low) & (close > prior_low)).astype(float)
        g["liquidity_sweep_score"] = ((g["sweep_high"] + g["sweep_low"]) * (candle_range / close.replace(0, np.nan))).fillna(0.0)

        # Market breadth proxy within each asset: trend/volume participation.
        g["volume_z_1d"] = self._rolling_z(volume, 96)
        g["range_z_1d"] = self._rolling_z(candle_range / close.replace(0, np.nan), 96)
        return g

    @staticmethod
    def _rolling_z(series: pd.Series, window: int) -> pd.Series:
        mean = series.rolling(window, min_periods=max(10, window // 4)).mean()
        std = series.rolling(window, min_periods=max(10, window // 4)).std().replace(0, np.nan)
        return ((series - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _load_external(self, source: object) -> pd.DataFrame:
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        elif isinstance(source, pl.DataFrame):
            df = source.to_pandas()
        else:
            path = Path(str(source))
            if path.suffix.lower() == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
        if "datetime" not in df.columns:
            for candidate in ("timestamp", "time", "date"):
                if candidate in df.columns:
                    df = df.rename(columns={candidate: "datetime"})
                    break
        if "datetime" not in df.columns:
            raise ValueError("External macro source requires datetime/timestamp column")
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        if "asset" in df.columns:
            df["asset"] = df["asset"].astype(str).str.upper().str.replace("/", "", regex=False)
        return df.sort_values([c for c in ["asset", "datetime"] if c in df.columns]).reset_index(drop=True)

    def _merge_asset_asof(self, base: pd.DataFrame, ext: pd.DataFrame, expected_columns: Tuple[str, ...]) -> pd.DataFrame:
        if "asset" not in ext.columns:
            # Treat as global data if asset column is absent.
            return self._merge_global_asof(base, ext, expected_columns)
        merge_cols = [c for c in expected_columns if c in ext.columns]
        if not merge_cols:
            return base
        parts = []
        right_all = ext[["asset", "datetime"] + merge_cols].copy()
        for asset, left_part in base.groupby("asset", sort=False):
            right_part = right_all[right_all["asset"] == asset].sort_values("datetime")
            left_part = left_part.sort_values("datetime")
            if right_part.empty:
                parts.append(left_part)
                continue
            merged = pd.merge_asof(
                left_part,
                right_part.drop(columns=["asset"]),
                on="datetime",
                direction="backward",
                allow_exact_matches=True,
            )
            parts.append(merged)
        return pd.concat(parts, ignore_index=True).sort_values(["asset", "datetime"]).reset_index(drop=True)

    def _merge_global_asof(self, base: pd.DataFrame, ext: pd.DataFrame, expected_columns: Tuple[str, ...]) -> pd.DataFrame:
        merge_cols = [c for c in expected_columns if c in ext.columns]
        if not merge_cols:
            return base
        left = base.sort_values("datetime").copy()
        right = ext[["datetime"] + merge_cols].sort_values("datetime").copy()
        merged = pd.merge_asof(left, right, on="datetime", direction="backward", allow_exact_matches=True)
        return merged.sort_values(["asset", "datetime"]).reset_index(drop=True)

    def _ensure_external_defaults(self, df: pd.DataFrame) -> pd.DataFrame:
        defaults = {
            "funding_rate": 0.0,
            "funding_rate_z": 0.0,
            "funding_available": 0.0,
            "open_interest": 0.0,
            "open_interest_change_1d": 0.0,
            "open_interest_available": 0.0,
            "btc_dominance": 0.0,
            "btc_dominance_change_1d": 0.0,
            "btc_dominance_available": 0.0,
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
        return df

    def _add_cross_asset_context(self, df: pd.DataFrame) -> pd.DataFrame:
        # BTC market beta proxy joined causally to all assets.
        if "return_1" not in df.columns:
            df["return_1"] = df.groupby("asset")["Close"].pct_change().fillna(0.0)
        btc = df[df["asset"] == self.config.btc_asset][["datetime", "return_1", "realized_vol_1d_ms", "htf_4h_trend"]].copy()
        if btc.empty:
            df["btc_return_1"] = 0.0
            df["btc_realized_vol_1d"] = 0.0
            df["btc_htf_4h_trend"] = 0.0
            df["asset_vs_btc_return_1"] = 0.0
            return df
        btc = btc.rename(columns={
            "return_1": "btc_return_1",
            "realized_vol_1d_ms": "btc_realized_vol_1d",
            "htf_4h_trend": "btc_htf_4h_trend",
        }).sort_values("datetime")
        left = df.sort_values("datetime").copy()
        merged = pd.merge_asof(left, btc, on="datetime", direction="backward", allow_exact_matches=True)
        merged["btc_return_1"] = pd.to_numeric(merged["btc_return_1"], errors="coerce").fillna(0.0)
        merged["btc_realized_vol_1d"] = pd.to_numeric(merged["btc_realized_vol_1d"], errors="coerce").fillna(0.0)
        merged["btc_htf_4h_trend"] = pd.to_numeric(merged["btc_htf_4h_trend"], errors="coerce").fillna(0.0)
        merged["asset_vs_btc_return_1"] = pd.to_numeric(merged.get("return_1", 0.0), errors="coerce").fillna(0.0) - merged["btc_return_1"]
        return merged.sort_values(["asset", "datetime"]).reset_index(drop=True)

    def _sanitize(self, df: pd.DataFrame) -> pd.DataFrame:
        numeric_cols = [c for c in df.columns if c not in {"datetime", "asset", "candidate_side", "volatility_regime", "market_regime", "label_reason", "label_end_time"}]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        fill_zero = [
            "realized_vol_1d_ms", "realized_vol_1w_ms", "volatility_compression",
            "is_vol_compressed", "is_vol_expanding", "htf_1h_return", "htf_4h_return",
            "htf_1h_trend", "htf_4h_trend", "htf_trend_alignment", "session_asia",
            "session_london", "session_ny", "session_overlap_london_ny", "day_of_week",
            "sweep_high", "sweep_low", "liquidity_sweep_score", "volume_z_1d", "range_z_1d",
            "btc_return_1", "btc_realized_vol_1d", "btc_htf_4h_trend", "asset_vs_btc_return_1",
        ]
        for col in fill_zero:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
        return df

    def build_report(self, enriched: pl.DataFrame, source_flags: Mapping[str, bool]) -> MarketStructureReport:
        feature_columns = {
            "realized_vol_1d_ms": "causal 1-day realized volatility proxy",
            "realized_vol_1w_ms": "causal 1-week realized volatility proxy",
            "volatility_compression": "current 1d realized vol / rolling median",
            "htf_1h_return": "1h rolling context return",
            "htf_4h_return": "4h rolling context return",
            "htf_trend_alignment": "1h/4h trend direction agreement",
            "session_asia/london/ny": "UTC trading session flags",
            "liquidity_sweep_score": "prior range sweep proxy",
            "funding_rate/open_interest/btc_dominance": "optional external macro features",
            "btc_return_1/btc_realized_vol_1d": "BTC market beta context",
        }
        cols_for_nulls = [c for c in enriched.columns if c not in ("datetime", "asset")]
        null_counts = {c: int(enriched[c].null_count()) for c in cols_for_nulls if c in enriched.columns}
        assets = {str(k): int(v) for k, v in enriched.group_by("asset").len().to_pandas().set_index("asset")["len"].to_dict().items()}
        warnings = []
        if not any(source_flags.values()):
            warnings.append("external_macro_sources_missing_using_ohlcv_proxies")
        if any(v > 0 for v in null_counts.values()):
            warnings.append("nulls_present_after_market_structure_enrichment")
        return MarketStructureReport(
            rows=enriched.height,
            assets=assets,
            feature_columns=feature_columns,
            external_sources=dict(source_flags),
            null_counts=null_counts,
            warnings=warnings,
        )

    def write_report(self, report: MarketStructureReport, path: Optional[str] = None) -> None:
        out = Path(path or self.config.output_report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
        print(f"  [MarketStructure] Report exported -> {out}")
