"""
core/correlation_engine.py — Institutional-Grade Asset Correlation Engine
========================================================================
Calculates rolling Pearson correlation matrices of asset returns and monitors
ARCH-style volatility clustering to identify systemic contagion risk.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


class CorrelationEngine:
    """
    Quantitative engine to calculate asset return correlations,
    volatility clustering, and render structural heatmaps.
    """

    def __init__(self, assets: List[str] = ["BTC", "ETH", "SOL", "XRP", "BNB"]):
        self.assets = assets
        # Historical prices cache: Dict[asset, Series]
        self.price_history: Dict[str, pd.Series] = {asset: pd.Series(dtype=float) for asset in assets}

    def update_prices(self, asset: str, datetime_series: pd.Series, close_series: pd.Series):
        """Appends price data for a specific asset aligned by datetime index."""
        # Ensure correct datatypes
        df = pd.DataFrame({"Close": close_series.values}, index=datetime_series)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        self.price_history[asset] = df["Close"]

    def calculate_returns(self, fill_method: str = "ffill") -> pd.DataFrame:
        """Aligns asset price series and computes percentage returns."""
        aligned_df = pd.DataFrame()
        for asset in self.assets:
            if not self.price_history[asset].empty:
                aligned_df[asset] = self.price_history[asset]
        
        if aligned_df.empty:
            return pd.DataFrame(columns=self.assets)

        # Forward fill to handle any asynchronous index gaps, then drop remaining NaNs
        if hasattr(aligned_df, fill_method):
            aligned_df = getattr(aligned_df, fill_method)().dropna()
        else:
            aligned_df = aligned_df.fillna(method=fill_method).dropna()
        returns_df = aligned_df.pct_change().dropna()
        return returns_df

    def get_correlation_matrix(self, returns_df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
        """
        Computes the rolling Pearson correlation matrix of returns.
        If returns_df contains insufficient rows, returns static default correlations.
        """
        if len(returns_df) < 5:
            # Default institutional fallback correlation matrix (highly correlated crypto market)
            default_matrix = pd.DataFrame(
                [
                    [1.00, 0.82, 0.71, 0.61, 0.68],
                    [0.82, 1.00, 0.75, 0.64, 0.70],
                    [0.71, 0.75, 1.00, 0.58, 0.65],
                    [0.61, 0.64, 0.58, 1.00, 0.59],
                    [0.68, 0.70, 0.65, 0.59, 1.00]
                ],
                index=self.assets,
                columns=self.assets
            )
            return default_matrix

        # Use recent window or entire history
        subset = returns_df.tail(window)
        corr_matrix = subset.corr(method="pearson")
        
        # Fill missing values if any asset has zero variance or missing data
        corr_matrix = corr_matrix.fillna(0.5)
        for i in range(len(corr_matrix)):
            corr_matrix.iloc[i, i] = 1.0
        return corr_matrix

    def get_volatility_clustering(self, returns_df: pd.DataFrame, window: int = 14) -> Dict[str, float]:
        """
        Identifies volatility clustering by computing the ratio of recent rolling volatility
        to historical volatility. If ratio > 1.5, volatility clustering is active.
        """
        clustering_status = {}
        if len(returns_df) < 20:
            return {asset: 1.0 for asset in self.assets}

        for asset in self.assets:
            if asset not in returns_df.columns:
                clustering_status[asset] = 1.0
                continue
            
            series = returns_df[asset]
            hist_vol = float(series.std())
            recent_vol = float(series.tail(window).std())
            
            if hist_vol > 0:
                clustering_status[asset] = float(recent_vol / hist_vol)
            else:
                clustering_status[asset] = 1.0

        return clustering_status

    def render_ascii_heatmap(self, corr_matrix: pd.DataFrame) -> str:
        """Renders a beautiful terminal-ready ASCII heatmap with color blocks."""
        # ANSI Escape Colors for ranges
        # [0.8, 1.0] -> Red / Dark Orange (highly correlated)
        # [0.5, 0.8] -> Yellow (moderately correlated)
        # [0.0, 0.5] -> Green (lowly correlated)
        # [-1.0, 0.0] -> Cyan (negatively correlated)
        
        lines = []
        lines.append("   " + "   ".join(self.assets))
        lines.append("  ┌" + "─────" * len(self.assets) + "┐")
        
        for asset_y in self.assets:
            row_str = f"{asset_y} │"
            for asset_x in self.assets:
                val = corr_matrix.loc[asset_y, asset_x]
                val_fmt = f"{val:+.2f}"
                
                # Apply ANSI Colors based on threshold
                if val == 1.0:
                    color = "\033[91m\033[1m" # Bold Red
                elif val >= 0.75:
                    color = "\033[91m"       # Red
                elif val >= 0.50:
                    color = "\033[93m"       # Yellow
                elif val >= 0.20:
                    color = "\033[92m"       # Green
                else:
                    color = "\033[96m"       # Cyan
                    
                row_str += f" {color}{val_fmt}\033[0m"
            row_str += " │"
            lines.append(row_str)
            
        lines.append("  └" + "─────" * len(self.assets) + "┘")
        return "\n".join(lines)
