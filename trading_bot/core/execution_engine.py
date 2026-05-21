"""
core/execution_engine.py — Execution Realism Orchestrator
=========================================================

This module connects the existing SlippageModel, LiquidityModel and
ExecutionAnalytics components into a single trade execution lifecycle.

Why this exists
---------------
The previous execution stack had strong individual components, but they were
mostly used as standalone diagnostics. A production backtest/live simulator
needs one deterministic path:

    signal price -> order simulation -> fill/no-fill -> execution record

Without that path, the strategy can still report optimistic fills, stale
slippage assumptions, or analytics with zero analysed trades. That creates fake
Sharpe and hides the true live/backtest execution gap.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from config import Config
from core.execution_analytics import ExecutionAnalytics, ExecutionRecord
from core.liquidity_model import FillResult, LiquidityModel
from core.slippage_model import SlippageEstimate, SlippageModel


@dataclass
class ExecutionOrder:
    """Canonical order request used by backtest, paper and live adapters."""

    trade_id: int
    timestamp: str
    asset: str
    side: str  # BUY | SELL
    theoretical_price: float
    size_notional: float
    atr_val: float
    atr_ratio: float = 1.0
    volume_ratio: float = 1.0
    market_regime: str = "RANGING"
    order_type: str = "LIMIT"  # LIMIT | MARKET | STOP
    entry_type: str = "BREAKOUT"  # BREAKOUT | LIMIT | MARKET
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class ExecutionFill:
    """Canonical execution result after slippage + liquidity simulation."""

    trade_id: int
    timestamp: str
    asset: str
    side: str
    requested_notional: float
    requested_price: float
    filled_size: float
    fill_price: float
    fill_pct: float
    notional_filled: float
    order_type: str
    vol_regime: str
    fill_delay_candles: int
    was_partial_fill: bool
    was_no_fill: bool
    slippage_bps: float
    liquidity_impact_bps: float
    total_execution_bps: float
    theoretical_price: float
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def is_filled(self) -> bool:
        return not self.was_no_fill and self.filled_size > 0.0


class ExecutionSimulationEngine:
    """
    Production-grade execution simulator for crypto futures backtests.

    The engine deliberately separates theoretical signal prices from actual
    simulated fills. All slippage and liquidity costs are adverse to the trade.
    This prevents the common failure mode where a backtest assumes the candle
    close is tradable with full size and zero queue/friction.
    """

    def __init__(
        self,
        slippage_model: Optional[SlippageModel] = None,
        liquidity_model: Optional[LiquidityModel] = None,
        analytics: Optional[ExecutionAnalytics] = None,
        commission_rate: Optional[float] = None,
        randomize: bool = True,
        random_seed: Optional[int] = None,
    ):
        self.slippage_model = slippage_model or SlippageModel(
            randomize=randomize,
            random_seed=random_seed,
        )
        self.liquidity_model = liquidity_model or LiquidityModel(
            randomize=randomize,
            random_seed=random_seed,
        )
        self.analytics = analytics or ExecutionAnalytics(
            commission_rate=commission_rate
            if commission_rate is not None
            else getattr(Config, "COMMISSION_RATE", 0.0004)
        )
        self.records: List[ExecutionFill] = []

    def simulate_entry(self, order: ExecutionOrder) -> ExecutionFill:
        """Simulate entry fill with volatility-aware slippage and liquidity."""
        self._validate_order(order)
        vol_regime = SlippageModel.vol_regime_from_atr_ratio(order.atr_ratio)

        liquidity = self.liquidity_model.simulate_fill(
            order_size_notional=order.size_notional,
            price=order.theoretical_price,
            volume_ratio=order.volume_ratio,
            vol_regime=vol_regime,
            order_type=order.order_type,
            side=order.side,
            entry_type=order.entry_type,
        )

        slippage = self.slippage_model.estimate_slippage(
            side=order.side,
            entry_price=order.theoretical_price,
            atr_val=order.atr_val,
            order_size_notional=order.size_notional * liquidity.fill_pct,
            vol_regime=vol_regime,
            order_type=order.order_type,
            entry_type=order.entry_type,
            atr_ratio=order.atr_ratio,
        )

        fill = self._combine_fill(order, liquidity, slippage, vol_regime)
        self.records.append(fill)
        return fill

    def simulate_exit(
        self,
        order: ExecutionOrder,
        exit_price: float,
        exit_type: str = "TIME",  # TP | SL | TIME
    ) -> ExecutionFill:
        """Simulate exit execution. Stop-loss exits use worse market-order semantics."""
        self._validate_order(order)
        if exit_price <= 0:
            raise ValueError("exit_price must be positive")

        vol_regime = SlippageModel.vol_regime_from_atr_ratio(order.atr_ratio)
        exit_side = "SELL" if order.side == "BUY" else "BUY"
        exit_order_type = "STOP" if exit_type == "SL" else ("LIMIT" if exit_type == "TP" else "MARKET")

        liquidity = self.liquidity_model.simulate_fill(
            order_size_notional=order.size_notional,
            price=exit_price,
            volume_ratio=order.volume_ratio,
            vol_regime=vol_regime,
            order_type=exit_order_type,
            side=exit_side,
            entry_type=exit_type,
        )

        slippage = self.slippage_model.estimate_exit_slippage(
            side=order.side,
            exit_price=exit_price,
            atr_val=order.atr_val,
            order_size_notional=order.size_notional * liquidity.fill_pct,
            vol_regime=vol_regime,
            exit_type=exit_type,
            atr_ratio=order.atr_ratio,
        )

        exit_order = ExecutionOrder(
            trade_id=order.trade_id,
            timestamp=order.timestamp,
            asset=order.asset,
            side=exit_side,
            theoretical_price=exit_price,
            size_notional=order.size_notional,
            atr_val=order.atr_val,
            atr_ratio=order.atr_ratio,
            volume_ratio=order.volume_ratio,
            market_regime=order.market_regime,
            order_type=exit_order_type,
            entry_type=exit_type,
            metadata={**order.metadata, "exit_type": exit_type},
        )

        fill = self._combine_fill(exit_order, liquidity, slippage, vol_regime)
        self.records.append(fill)
        return fill

    def record_round_trip(
        self,
        entry_order: ExecutionOrder,
        entry_fill: ExecutionFill,
        exit_fill: ExecutionFill,
        theoretical_exit: float,
    ) -> Optional[ExecutionRecord]:
        """
        Push a complete trade into ExecutionAnalytics.

        Returns None for no-fill entries because no trade lifecycle exists. This
        prevents analytics from counting missed entries as executed trades while
        still keeping no-fill diagnostics in self.records.
        """
        if not entry_fill.is_filled:
            return None

        entry_slip = self._slippage_from_fill(entry_order, entry_fill)
        exit_slip = self._slippage_from_fill(
            ExecutionOrder(
                trade_id=entry_order.trade_id,
                timestamp=entry_order.timestamp,
                asset=entry_order.asset,
                side="SELL" if entry_order.side == "BUY" else "BUY",
                theoretical_price=theoretical_exit,
                size_notional=entry_fill.notional_filled,
                atr_val=entry_order.atr_val,
                atr_ratio=entry_order.atr_ratio,
                volume_ratio=entry_order.volume_ratio,
                market_regime=entry_order.market_regime,
                order_type=exit_fill.order_type,
                entry_type=str(exit_fill.metadata.get("exit_type", "TIME")),
            ),
            exit_fill,
        )

        requested_size = entry_fill.requested_notional / entry_order.theoretical_price
        return self.analytics.record_from_slippage(
            side=entry_order.side,
            regime=entry_order.market_regime,
            vol_regime=entry_fill.vol_regime,
            theoretical_entry=entry_order.theoretical_price,
            theoretical_exit=theoretical_exit,
            entry_slip=entry_slip,
            exit_slip=exit_slip,
            fill_result=FillResult(
                requested_size=entry_fill.requested_notional / entry_order.theoretical_price,
                requested_price=entry_order.theoretical_price,
                filled_size=entry_fill.filled_size,
                fill_price=entry_fill.fill_price,
                fill_pct=entry_fill.fill_pct,
                is_complete_fill=not entry_fill.was_partial_fill and not entry_fill.was_no_fill,
                is_partial_fill=entry_fill.was_partial_fill,
                is_no_fill=entry_fill.was_no_fill,
                fill_delay_candles=entry_fill.fill_delay_candles,
                total_impact_bps=entry_fill.liquidity_impact_bps,
                vol_regime=entry_fill.vol_regime,
            ),
            size=requested_size,
            atr_val=entry_order.atr_val,
            timestamp=entry_order.timestamp,
        )

    def export_execution_report(self, path: str = "data/execution_reports.json") -> Dict[str, object]:
        """Export order-level and aggregate execution diagnostics."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        summary = self.analytics.compute_summary()
        payload = {
            "timestamp": datetime.now().isoformat(),
            "orders_simulated": len(self.records),
            "filled_orders": sum(1 for r in self.records if r.is_filled),
            "partial_fills": sum(1 for r in self.records if r.was_partial_fill),
            "no_fills": sum(1 for r in self.records if r.was_no_fill),
            "avg_total_execution_bps": self._mean([r.total_execution_bps for r in self.records]),
            "by_vol_regime": self._group_avg_execution_bps(),
            "analytics_summary": asdict(summary),
            "records": [asdict(r) for r in self.records],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return payload

    def _combine_fill(
        self,
        order: ExecutionOrder,
        liquidity: FillResult,
        slippage: SlippageEstimate,
        vol_regime: str,
    ) -> ExecutionFill:
        if liquidity.is_no_fill:
            fill_price = 0.0
            notional_filled = 0.0
        else:
            # Add liquidity impact to the already adverse slippage price.
            impact_px = SlippageModel.bps_to_price(liquidity.total_impact_bps, order.theoretical_price)
            if order.side == "BUY":
                fill_price = slippage.adjusted_price + impact_px
            else:
                fill_price = slippage.adjusted_price - impact_px
            notional_filled = liquidity.filled_size * fill_price

        return ExecutionFill(
            trade_id=order.trade_id,
            timestamp=order.timestamp,
            asset=order.asset,
            side=order.side,
            requested_notional=order.size_notional,
            requested_price=order.theoretical_price,
            filled_size=liquidity.filled_size,
            fill_price=fill_price,
            fill_pct=liquidity.fill_pct,
            notional_filled=notional_filled,
            order_type=liquidity.order_type,
            vol_regime=vol_regime,
            fill_delay_candles=liquidity.fill_delay_candles,
            was_partial_fill=liquidity.is_partial_fill,
            was_no_fill=liquidity.is_no_fill,
            slippage_bps=slippage.total_slippage_bps,
            liquidity_impact_bps=liquidity.total_impact_bps,
            total_execution_bps=slippage.total_slippage_bps + liquidity.total_impact_bps,
            theoretical_price=order.theoretical_price,
            metadata=order.metadata,
        )

    def _slippage_from_fill(self, order: ExecutionOrder, fill: ExecutionFill) -> SlippageEstimate:
        adverse_px = abs(fill.fill_price - order.theoretical_price) if fill.is_filled else 0.0
        adjusted_price = fill.fill_price if fill.is_filled else order.theoretical_price
        return SlippageEstimate(
            theoretical_price=order.theoretical_price,
            side=order.side,
            order_type=fill.order_type,
            half_spread=SlippageModel.bps_to_price(fill.slippage_bps * 0.25, order.theoretical_price),
            base_slippage=SlippageModel.bps_to_price(fill.slippage_bps * 0.50, order.theoretical_price),
            volume_impact=SlippageModel.bps_to_price(fill.liquidity_impact_bps, order.theoretical_price),
            urgency_premium=SlippageModel.bps_to_price(fill.slippage_bps * 0.25, order.theoretical_price),
            total_slippage_price=adverse_px,
            adjusted_price=adjusted_price,
            total_slippage_bps=fill.total_execution_bps,
            total_cost_pct=fill.total_execution_bps / 100.0,
            vol_regime=fill.vol_regime,
            atr_ratio=order.atr_ratio,
        )

    @staticmethod
    def _validate_order(order: ExecutionOrder) -> None:
        if order.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if order.order_type not in {"LIMIT", "MARKET", "STOP"}:
            raise ValueError("order_type must be LIMIT, MARKET or STOP")
        if order.theoretical_price <= 0:
            raise ValueError("theoretical_price must be positive")
        if order.size_notional <= 0:
            raise ValueError("size_notional must be positive")
        if order.atr_val < 0:
            raise ValueError("atr_val cannot be negative")

    @staticmethod
    def _mean(values: List[float]) -> float:
        return float(sum(values) / len(values)) if values else 0.0

    def _group_avg_execution_bps(self) -> Dict[str, float]:
        groups: Dict[str, List[float]] = {}
        for record in self.records:
            groups.setdefault(record.vol_regime, []).append(record.total_execution_bps)
        return {k: self._mean(v) for k, v in groups.items()}
