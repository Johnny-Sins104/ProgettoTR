"""
core/portfolio_risk_engine.py — Portfolio Risk + Cross-Asset Exposure Engine
============================================================================

This module hardens the existing PortfolioManager/ExposureTracker layer by
adding a stateful event pipeline:

    proposed trade -> portfolio gate -> open event -> exposure snapshot
    -> close event -> portfolio/risk report

The goal is to avoid disconnected analytics where trades execute but portfolio
or risk diagnostics show zero analysed trades. Institutional systems treat
exposure as a continuously updated state, not as an end-of-backtest summary.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.correlation_engine import CorrelationEngine
from core.portfolio_manager import PortfolioManager


@dataclass
class PositionState:
    asset: str
    side: str
    size: float
    entry: float
    notional: float
    status: str = "ACTIVE"
    opened_at: str = ""
    regime: str = "UNKNOWN"
    trade_id: Optional[int] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class PortfolioRiskSnapshot:
    timestamp: str
    balance: float
    total_notional: float
    aggregate_leverage: float
    portfolio_var: float
    var_limit: float
    active_positions: int
    gross_exposure: float
    net_directional_exposure: float
    max_asset_weight_pct: float
    max_pairwise_correlation: float
    concentration_flags: List[str] = field(default_factory=list)
    exposures: Dict[str, dict] = field(default_factory=dict)


class PortfolioRiskEngine:
    """Stateful portfolio-risk controller for multi-asset crypto futures."""

    def __init__(
        self,
        assets: Optional[List[str]] = None,
        balance: float = 10_000.0,
        var_confidence: float = 0.95,
        var_limit_pct: float = 0.05,
        max_aggregate_leverage: float = 5.0,
    ):
        self.assets = assets or ["BTC", "ETH", "SOL", "XRP", "BNB"]
        self.balance = float(balance)
        self.manager = PortfolioManager(
            assets=self.assets,
            var_confidence=var_confidence,
            var_limit_pct=var_limit_pct,
            max_aggregate_leverage=max_aggregate_leverage,
        )
        self.correlation_engine = CorrelationEngine(self.assets)
        self.positions: Dict[str, PositionState] = {}
        self.snapshots: List[PortfolioRiskSnapshot] = []
        self.events: List[Dict[str, object]] = []

    def update_market_data(
        self,
        asset: str,
        datetime_series,
        close_series,
    ) -> None:
        """Feed latest price history into the rolling correlation engine."""
        if asset not in self.assets:
            raise ValueError(f"Unsupported asset: {asset}")
        self.correlation_engine.update_prices(asset, datetime_series, close_series)

    def evaluate_trade(
        self,
        asset: str,
        side: str,
        proposed_notional: float,
        current_prices: Dict[str, float],
        timestamp: Optional[str] = None,
    ) -> Tuple[bool, float, List[str]]:
        """Evaluate a proposed trade against leverage, sector, correlation and VaR."""
        timestamp = timestamp or datetime.now().isoformat()
        active_positions = self._positions_for_legacy_api()
        returns_df = self.correlation_engine.calculate_returns()
        corr_matrix = self._safe_corr_matrix(returns_df)

        allowed, multiplier, reasons = self.manager.evaluate_proposed_trade(
            asset=asset,
            side=side,
            proposed_notional=proposed_notional,
            active_positions=active_positions,
            current_prices=current_prices,
            corr_matrix=corr_matrix,
            returns_df=returns_df,
            balance=self.balance,
        )

        self.events.append({
            "timestamp": timestamp,
            "event_type": "EVALUATE_TRADE",
            "asset": asset,
            "side": side,
            "proposed_notional": proposed_notional,
            "allowed": allowed,
            "size_multiplier": multiplier,
            "reasons": reasons,
        })
        return allowed, multiplier, reasons

    def open_position(
        self,
        asset: str,
        side: str,
        size: float,
        entry_price: float,
        current_prices: Dict[str, float],
        timestamp: Optional[str] = None,
        regime: str = "UNKNOWN",
        trade_id: Optional[int] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> PortfolioRiskSnapshot:
        """Register an executed fill and immediately update portfolio exposure."""
        timestamp = timestamp or datetime.now().isoformat()
        if asset not in self.assets:
            raise ValueError(f"Unsupported asset: {asset}")
        if size <= 0 or entry_price <= 0:
            raise ValueError("size and entry_price must be positive")

        notional = float(size * entry_price)
        self.positions[asset] = PositionState(
            asset=asset,
            side=side,
            size=float(size),
            entry=float(entry_price),
            notional=notional,
            opened_at=timestamp,
            regime=regime,
            trade_id=trade_id,
            metadata=metadata or {},
        )
        self.events.append({
            "timestamp": timestamp,
            "event_type": "OPEN_POSITION",
            "asset": asset,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "notional": notional,
            "trade_id": trade_id,
        })
        return self.snapshot(current_prices=current_prices, timestamp=timestamp)

    def close_position(
        self,
        asset: str,
        exit_price: float,
        current_prices: Dict[str, float],
        timestamp: Optional[str] = None,
        fees: float = 0.0,
    ) -> Tuple[float, PortfolioRiskSnapshot]:
        """Close an active position, update balance and emit a new exposure snapshot."""
        timestamp = timestamp or datetime.now().isoformat()
        pos = self.positions.get(asset)
        if pos is None or pos.status != "ACTIVE":
            raise ValueError(f"No active position for {asset}")
        if exit_price <= 0:
            raise ValueError("exit_price must be positive")

        if pos.side == "BUY":
            pnl = (exit_price - pos.entry) * pos.size
        else:
            pnl = (pos.entry - exit_price) * pos.size
        pnl -= fees
        self.balance += pnl

        self.events.append({
            "timestamp": timestamp,
            "event_type": "CLOSE_POSITION",
            "asset": asset,
            "side": pos.side,
            "entry_price": pos.entry,
            "exit_price": exit_price,
            "size": pos.size,
            "pnl": pnl,
            "fees": fees,
            "trade_id": pos.trade_id,
        })
        del self.positions[asset]
        snap = self.snapshot(current_prices=current_prices, timestamp=timestamp)
        return pnl, snap

    def snapshot(
        self,
        current_prices: Dict[str, float],
        timestamp: Optional[str] = None,
    ) -> PortfolioRiskSnapshot:
        """Compute and store a point-in-time portfolio risk snapshot."""
        timestamp = timestamp or datetime.now().isoformat()
        active_positions = self._positions_for_legacy_api()
        exposures = self.manager.tracker.calculate_exposures(
            active_positions,
            current_prices,
            self.balance,
        )
        returns_df = self.correlation_engine.calculate_returns()
        corr_matrix = self._safe_corr_matrix(returns_df)
        weights = self._weights_from_positions(current_prices)
        portfolio_var = self.manager.calculate_portfolio_var(weights, returns_df, self.balance)

        total_notional = float(exposures["GLOBAL"]["total_notional"])
        gross_exposure = total_notional / self.balance if self.balance > 0 else 0.0
        net_directional = self._net_directional_exposure(current_prices)
        max_asset_weight = max(
            [v.get("weight_pct", 0.0) for k, v in exposures.items() if k != "GLOBAL"],
            default=0.0,
        )
        flags = self._concentration_flags(exposures, corr_matrix)
        snapshot = PortfolioRiskSnapshot(
            timestamp=timestamp,
            balance=self.balance,
            total_notional=total_notional,
            aggregate_leverage=float(exposures["GLOBAL"]["aggregate_leverage"]),
            portfolio_var=float(portfolio_var),
            var_limit=float(self.balance * self.manager.var_limit_pct),
            active_positions=len(self.positions),
            gross_exposure=float(gross_exposure),
            net_directional_exposure=float(net_directional),
            max_asset_weight_pct=float(max_asset_weight),
            max_pairwise_correlation=self._max_pairwise_correlation(corr_matrix),
            concentration_flags=flags,
            exposures=exposures,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def export_report(self, path: str = "data/portfolio_risk_report.json") -> Dict[str, object]:
        """Export portfolio risk state, event history and diagnostics."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "assets": self.assets,
            "balance": self.balance,
            "events_recorded": len(self.events),
            "snapshots_recorded": len(self.snapshots),
            "active_positions": {k: asdict(v) for k, v in self.positions.items()},
            "latest_snapshot": asdict(self.snapshots[-1]) if self.snapshots else None,
            "events": self.events,
            "snapshots": [asdict(s) for s in self.snapshots],
            "diagnostics": self._diagnostics(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return payload

    def _positions_for_legacy_api(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for asset, pos in self.positions.items():
            out[asset] = {
                "status": pos.status,
                "size": pos.size,
                "side": pos.side,
                "entry": pos.entry,
                "regime": pos.regime,
                "trade_id": pos.trade_id,
            }
        return out

    def _weights_from_positions(self, current_prices: Dict[str, float]) -> np.ndarray:
        weights = np.zeros(len(self.assets))
        for idx, asset in enumerate(self.assets):
            pos = self.positions.get(asset)
            if pos and self.balance > 0:
                price = float(current_prices.get(asset, pos.entry))
                weights[idx] = (pos.size * price) / self.balance
        return weights

    def _net_directional_exposure(self, current_prices: Dict[str, float]) -> float:
        net = 0.0
        for asset, pos in self.positions.items():
            price = float(current_prices.get(asset, pos.entry))
            signed = pos.size * price
            net += signed if pos.side == "BUY" else -signed
        return net / self.balance if self.balance > 0 else 0.0

    def _safe_corr_matrix(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        if returns_df is None or returns_df.empty:
            return pd.DataFrame(np.eye(len(self.assets)), index=self.assets, columns=self.assets)
        corr = self.correlation_engine.get_correlation_matrix(returns_df)
        return corr.reindex(index=self.assets, columns=self.assets).fillna(0.0).replace(0.0, np.nan).fillna(
            pd.DataFrame(np.eye(len(self.assets)), index=self.assets, columns=self.assets)
        )

    def _max_pairwise_correlation(self, corr_matrix: pd.DataFrame) -> float:
        vals = []
        for i, a in enumerate(self.assets):
            for b in self.assets[i + 1 :]:
                if a in corr_matrix.index and b in corr_matrix.columns:
                    vals.append(abs(float(corr_matrix.loc[a, b])))
        return max(vals) if vals else 0.0

    def _concentration_flags(self, exposures: Dict[str, dict], corr_matrix: pd.DataFrame) -> List[str]:
        flags: List[str] = []
        if exposures["GLOBAL"].get("aggregate_leverage", 0.0) > self.manager.max_aggregate_leverage:
            flags.append("AGGREGATE_LEVERAGE_LIMIT_EXCEEDED")
        for asset, data in exposures.items():
            if asset != "GLOBAL" and data.get("weight_pct", 0.0) > 35.0:
                flags.append(f"HIGH_SINGLE_ASSET_WEIGHT:{asset}")
        if self._max_pairwise_correlation(corr_matrix) > 0.85 and len(self.positions) >= 2:
            flags.append("HIGH_CORRELATION_CLUSTER")
        latest_var = self.snapshots[-1].portfolio_var if self.snapshots else 0.0
        if latest_var > self.balance * self.manager.var_limit_pct:
            flags.append("VAR_LIMIT_EXCEEDED")
        return flags

    def _diagnostics(self) -> Dict[str, object]:
        if not self.snapshots:
            return {"status": "NO_SNAPSHOTS"}
        leverages = [s.aggregate_leverage for s in self.snapshots]
        vars_ = [s.portfolio_var for s in self.snapshots]
        return {
            "max_aggregate_leverage": max(leverages),
            "avg_aggregate_leverage": float(sum(leverages) / len(leverages)),
            "max_portfolio_var": max(vars_),
            "avg_portfolio_var": float(sum(vars_) / len(vars_)),
            "max_active_positions": max(s.active_positions for s in self.snapshots),
            "flag_count": sum(len(s.concentration_flags) for s in self.snapshots),
        }
