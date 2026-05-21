"""Integration smoke tests for Prompt 15 and Prompt 16 engines."""

from datetime import datetime

import numpy as np
import pandas as pd

from core.execution_engine import ExecutionOrder, ExecutionSimulationEngine
from core.portfolio_risk_engine import PortfolioRiskEngine


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


print("\n=== Prompt 15 — ExecutionSimulationEngine ===")
execution = ExecutionSimulationEngine(randomize=False, random_seed=42)
order = ExecutionOrder(
    trade_id=1,
    timestamp=datetime.now().isoformat(),
    asset="BTC",
    side="BUY",
    theoretical_price=65_000.0,
    size_notional=5_000.0,
    atr_val=500.0,
    atr_ratio=1.6,
    volume_ratio=1.0,
    market_regime="TRENDING",
    order_type="MARKET",
    entry_type="BREAKOUT",
)
entry = execution.simulate_entry(order)
check(entry.is_filled, "market entry fills")
check(entry.fill_price > order.theoretical_price, "BUY fill price is adverse after costs")
exit_fill = execution.simulate_exit(order, exit_price=66_000.0, exit_type="TP")
check(exit_fill.is_filled, "exit fills")
rec = execution.record_round_trip(order, entry, exit_fill, theoretical_exit=66_000.0)
check(rec is not None, "execution analytics receives completed round trip")
report = execution.export_execution_report("data/test_execution_reports.json")
check(report["orders_simulated"] == 2, "execution report exports order records")

print("\n=== Prompt 16 — PortfolioRiskEngine ===")
assets = ["BTC", "ETH", "SOL", "XRP", "BNB"]
portfolio = PortfolioRiskEngine(assets=assets, balance=10_000.0, max_aggregate_leverage=3.0)
idx = pd.date_range("2024-01-01", periods=120, freq="15min")
rng = np.random.default_rng(42)
base = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
for i, asset in enumerate(assets):
    prices = pd.Series(base * (1 + 0.01 * i) + rng.normal(0, 0.5, len(idx)), index=idx)
    portfolio.update_market_data(asset, idx, prices)
current_prices = {"BTC": 65_000.0, "ETH": 3_500.0, "SOL": 160.0, "XRP": 0.65, "BNB": 600.0}
allowed, mult, reasons = portfolio.evaluate_trade("BTC", "BUY", 2_000.0, current_prices)
check(mult >= 0.0, "portfolio gate returns valid multiplier")
snap = portfolio.open_position("BTC", "BUY", size=0.03, entry_price=65_000.0, current_prices=current_prices)
check(snap.active_positions == 1, "open position updates active exposure")
check(snap.total_notional > 0, "snapshot tracks total notional")
pnl, snap2 = portfolio.close_position("BTC", exit_price=66_000.0, current_prices=current_prices)
check(snap2.active_positions == 0, "close position clears exposure")
report2 = portfolio.export_report("data/test_portfolio_risk_report.json")
check(report2["events_recorded"] >= 3, "portfolio report exports lifecycle events")

print("\nPrompt 15/16 integration smoke tests passed.")
