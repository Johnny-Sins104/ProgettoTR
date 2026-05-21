"""
core/portfolio_manager.py — Institutional Portfolio Risk Manager & Allocator
========================================================================
Implements portfolio Value at Risk (VaR) limits, dynamic risk-parity weight
allocation, and aggregate portfolio leverage circuit-breakers.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from config import Config
from core.exposure_tracker import ExposureTracker


class PortfolioManager:
    """
    Central quantitative orchestrator that manages multi-asset position compliance,
    VaR gating, and aggregate risk limits.
    """

    def __init__(
        self, 
        assets: List[str] = ["BTC", "ETH", "SOL", "XRP", "BNB"],
        var_confidence: float = 0.95,
        var_limit_pct: float = 0.05,       # Max portfolio VaR <= 5% of balance
        max_aggregate_leverage: float = 5.0 # Absolute aggregate leverage cap
    ):
        self.assets = assets
        self.var_confidence = var_confidence
        self.var_limit_pct = var_limit_pct
        self.max_aggregate_leverage = max_aggregate_leverage
        
        self.tracker = ExposureTracker(assets)

    def calculate_portfolio_var(
        self, 
        weights: np.ndarray, 
        returns_df: pd.DataFrame,
        balance: float
    ) -> float:
        """
        Computes the portfolio Value at Risk (VaR) using a Parametric (Variance-Covariance) method.
        Returns the absolute VaR value in cash currency.
        """
        if len(returns_df) < 10 or len(returns_df.columns) == 0:
            # Fallback VaR estimation (e.g. simple 2% of total portfolio value)
            return float(balance * 0.02)

        # Align weights with returns dataframe columns
        active_assets = [col for col in returns_df.columns if col in self.assets]
        if not active_assets:
            return float(balance * 0.02)

        # Subset weights corresponding to columns
        w_dict = {asset: weights[i] for i, asset in enumerate(self.assets)}
        subset_w = np.array([w_dict.get(asset, 0.0) for asset in active_assets])
        
        # Avoid division by zero: if all weights are zero, VaR is zero
        w_sum = subset_w.sum()
        if w_sum > 0:
            subset_w = subset_w / w_sum  # normalize to sum to 1
        else:
            return 0.0

        # Calculate covariance matrix of aligned assets
        cov_matrix = returns_df[active_assets].cov().values
        
        # Portfolio Variance: W^T * Sigma * W
        portfolio_var = np.dot(subset_w.T, np.dot(cov_matrix, subset_w))
        # Scale 15m returns standard deviation to 1-day (96 candles per day)
        portfolio_std = np.sqrt(max(0.0, portfolio_var)) * np.sqrt(96)
        
        # Z-score for normal distribution (95% -> 1.64485)
        # We model 1-day horizon VaR
        z_score = 1.64485 if self.var_confidence == 0.95 else 2.32635
        
        # VaR = z * portfolio_std * Portfolio Value (total active notional)
        total_active_notional = w_sum * balance
        var_value = float(z_score * portfolio_std * total_active_notional)
        
        return var_value

    def optimize_weights_risk_parity(
        self, 
        returns_df: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Computes dynamic inverse-volatility weights across assets.
        This provides risk-parity sizing, allocating more capital to lower-volatility assets.
        """
        if len(returns_df) < 10:
            # Static equal weight fallback
            eq_weight = 1.0 / len(self.assets)
            return {asset: eq_weight for asset in self.assets}

        volatilities = {}
        total_inv_vol = 0.0

        for asset in self.assets:
            if asset in returns_df.columns:
                std = float(returns_df[asset].std())
                # Handle zero variance safety check
                vol = std if std > 0.0001 else 0.05
                inv_vol = 1.0 / vol
                volatilities[asset] = inv_vol
                total_inv_vol += inv_vol
            else:
                # Missing asset fallback std
                volatilities[asset] = 1.0 / 0.05
                total_inv_vol += (1.0 / 0.05)

        # Normalize weights so they sum to 1.0
        weights = {}
        for asset in self.assets:
            weights[asset] = volatilities[asset] / total_inv_vol if total_inv_vol > 0 else 0.20

        return weights

    def evaluate_proposed_trade(
        self,
        asset: str,
        side: str,
        proposed_notional: float,
        active_positions: Dict[str, dict],
        current_prices: Dict[str, float],
        corr_matrix: pd.DataFrame,
        returns_df: pd.DataFrame,
        balance: float
    ) -> Tuple[bool, float, List[str]]:
        """
        Core portfolio gating mechanism. Evaluates a proposed trade candidate against
        aggregate leverage limits, VaR budgets, sector clustering, and correlation caps.
        
        Returns:
          - is_allowed: bool
          - size_multiplier: float (0.0 to 1.0, to scale down position if minor limits are violated)
          - reasons: List[str] containing warning/diagnostic messages.
        """
        reasons = []
        is_allowed = True
        scale_factor = 1.0

        # Update current exposures
        exposures = self.tracker.calculate_exposures(active_positions, current_prices, balance)
        current_global_notional = exposures["GLOBAL"]["total_notional"]
        
        # ── 1. AGGREGATE LEVERAGE CHECK ──
        projected_global_notional = current_global_notional + proposed_notional
        projected_aggregate_leverage = projected_global_notional / balance if balance > 0 else 0.0
        
        if projected_aggregate_leverage > self.max_aggregate_leverage:
            headroom = max(0.0, (self.max_aggregate_leverage * balance) - current_global_notional)
            if headroom == 0.0:
                reasons.append(f"Aggregate leverage cap {self.max_aggregate_leverage}x fully saturated.")
                return False, 0.0, reasons
            else:
                scale_factor = headroom / proposed_notional
                is_allowed = False
                reasons.append(f"Leverage limit exceeded ({projected_aggregate_leverage:.2f}x > {self.max_aggregate_leverage}x). Scaling trade size.")

        # ── 2. SECTOR CAP LIMITS ──
        sec_ok, sec_reason, sec_scale = self.tracker.check_sector_limits(
            proposed_asset=asset,
            proposed_notional=proposed_notional * scale_factor,
            exposures=exposures,
            balance=balance
        )
        if not sec_ok:
            scale_factor *= sec_scale
            if sec_scale == 0.0:
                is_allowed = False
            reasons.append(sec_reason)

        # ── 3. CORRELATION CO-MOVEMENT CHECK ──
        corr_ok, corr_reason, corr_scale = self.tracker.check_correlation_limits(
            proposed_asset=asset,
            proposed_side=side,
            proposed_notional=proposed_notional * scale_factor,
            positions=active_positions,
            corr_matrix=corr_matrix
        )
        if not corr_ok:
            scale_factor *= corr_scale
            reasons.append(corr_reason)

        # ── 4. PORTFOLIO VALUE AT RISK (VaR) GATE ──
        # Build weight vector representing projected portfolio state
        projected_weights = np.zeros(len(self.assets))
        for idx, a in enumerate(self.assets):
            pos = active_positions.get(a)
            weight = 0.0
            if a == asset:
                weight = (proposed_notional * scale_factor) / balance
            elif pos and pos.get("status") == "ACTIVE":
                price = current_prices.get(a, pos["entry"])
                weight = (pos["size"] * price) / balance
            projected_weights[idx] = weight

        projected_var = self.calculate_portfolio_var(projected_weights, returns_df, balance)
        max_var_allowed = balance * self.var_limit_pct
        
        if projected_var > max_var_allowed:
            is_allowed = False
            var_scale = max_var_allowed / projected_var if projected_var > 0 else 0.0
            scale_factor *= var_scale
            reasons.append(
                f"VaR budget exceeded (Projected VaR: {projected_var:.2f} EUR > "
                f"Limit: {max_var_allowed:.2f} EUR). Gating/Scaling position."
            )

        return is_allowed, max(0.0, float(scale_factor)), reasons
