"""
core/exposure_tracker.py — Portfolio Exposure & Sector Clustering Tracker
========================================================================
Monages multi-asset notional exposures, directional net positions, sector
concentration caps, and flags co-moving systematic correlation risk.
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple


class ExposureTracker:
    """
    Enforces compliance boundaries for asset sector allocation, regime concentration,
    and highly correlated co-directional trades.
    """

    SECTORS = {
        "BTC": "L1_MAJOR",
        "ETH": "L1_MAJOR",
        "SOL": "L1_ALT",
        "XRP": "PAYMENTS",
        "BNB": "UTILITY"
    }

    SECTOR_LIMITS = {
        "L1_MAJOR": 0.50,  # Max 50% notional portfolio allocation for L1 Majors
        "L1_ALT": 0.35,    # Max 35% for L1 Alts
        "PAYMENTS": 0.30,  # Max 30% for DeFi/Payments
        "UTILITY": 0.30    # Max 30% for Exchange utility tokens
    }

    def __init__(self, assets: List[str] = ["BTC", "ETH", "SOL", "XRP", "BNB"]):
        self.assets = assets

    def calculate_exposures(
        self, 
        positions: Dict[str, dict], 
        current_prices: Dict[str, float], 
        balance: float
    ) -> Dict[str, dict]:
        """
        Calculates exposure analytics for active positions: notional value, leverage,
        and portfolio weights.
        """
        exposure_report = {}
        total_notional = 0.0

        for asset in self.assets:
            pos = positions.get(asset)
            if pos and pos.get("status") == "ACTIVE":
                size = float(pos["size"])
                price = float(current_prices.get(asset, pos["entry"]))
                side = pos["side"]
                
                notional = size * price
                weight = notional / balance if balance > 0 else 0.0
                total_notional += notional

                exposure_report[asset] = {
                    "active": True,
                    "side": side,
                    "size": size,
                    "notional": notional,
                    "weight_pct": weight * 100.0,
                    "sector": self.SECTORS.get(asset, "OTHER")
                }
            else:
                exposure_report[asset] = {
                    "active": False,
                    "side": None,
                    "size": 0.0,
                    "notional": 0.0,
                    "weight_pct": 0.0,
                    "sector": self.SECTORS.get(asset, "OTHER")
                }

        exposure_report["GLOBAL"] = {
            "total_notional": total_notional,
            "aggregate_leverage": total_notional / balance if balance > 0 else 0.0,
            "cash_balance": balance
        }

        return exposure_report

    def check_sector_limits(
        self, 
        proposed_asset: str, 
        proposed_notional: float, 
        exposures: Dict[str, dict], 
        balance: float
    ) -> Tuple[bool, str, float]:
        """
        Verifies that adding a proposed position will not violate sector allocation caps.
        Returns (is_compliant, reason_string, scale_factor).
        """
        proposed_sector = self.SECTORS.get(proposed_asset, "OTHER")
        limit_pct = self.SECTOR_LIMITS.get(proposed_sector, 0.30)
        max_notional_allowed = balance * limit_pct

        # Sum active exposures in same sector
        current_sector_notional = 0.0
        for asset, data in exposures.items():
            if asset != "GLOBAL" and data.get("active") and data.get("sector") == proposed_sector:
                current_sector_notional += data["notional"]

        projected_sector_notional = current_sector_notional + proposed_notional
        if projected_sector_notional > max_notional_allowed:
            headroom = max(0.0, max_notional_allowed - current_sector_notional)
            if headroom == 0.0:
                return False, f"Sector limit {proposed_sector} saturated (cap: {limit_pct*100}%).", 0.0
            
            # Suggest scaling trade down to fit the headroom
            scale_factor = headroom / proposed_notional
            return False, f"Sector cap limit exceeded. Scaling down to fit headroom.", scale_factor

        return True, "Sector exposure compliant.", 1.0

    def check_correlation_limits(
        self,
        proposed_asset: str,
        proposed_side: str,
        proposed_notional: float,
        positions: Dict[str, dict],
        corr_matrix: pd.DataFrame,
        scale_on_violation: float = 0.70  # Default 30% reduction (scale to 70%)
    ) -> Tuple[bool, str, float]:
        """
        Checks if the proposed trade triggers co-directional risk with highly correlated
        existing positions (e.g., adding an ETH Long when we already hold a BTC Long and correlation > 0.75).
        """
        violations = []
        scale_factor = 1.0

        for active_asset in self.assets:
            if active_asset == proposed_asset:
                continue
                
            pos = positions.get(active_asset)
            if pos and pos.get("status") == "ACTIVE":
                corr = corr_matrix.loc[proposed_asset, active_asset]
                active_side = pos["side"]
                
                # Highly correlated asset in the same direction
                if corr > 0.70 and active_side == proposed_side:
                    violations.append(f"{active_asset} ({active_side}, corr: {corr:.2f})")
                    scale_factor *= scale_on_violation

        if violations:
            violation_str = ", ".join(violations)
            return (
                False, 
                f"Correlation co-movement risk with: {violation_str}. Scaling exposure.", 
                max(0.2, scale_factor)
            )

        return True, "No correlation co-movement violation.", 1.0

    def check_regime_concentration(
        self,
        positions: Dict[str, dict],
        regimes: Dict[str, str]
    ) -> Tuple[bool, str]:
        """
        Prevents risk concentration by alerting if more than 3 active assets are in the
        exact same market regime (e.g., all routed to HIGH_VOL).
        """
        active_regimes = {}
        for asset in self.assets:
            pos = positions.get(asset)
            if pos and pos.get("status") == "ACTIVE":
                r = regimes.get(asset, "UNIFIED")
                active_regimes[r] = active_regimes.get(r, 0) + 1

        for r, count in active_regimes.items():
            if count >= 3:
                return False, f"Concentrated regime risk: {count} assets in {r} regime."

        return True, "Regime concentration compliant."
