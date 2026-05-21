"""
run_portfolio_backtest.py — Multi-Asset Portfolio Engineering & Benchmark Simulator
==================================================================================
Simulates a multi-asset quantitative trading system across BTC, ETH, SOL, XRP, BNB.
Benchmarks an Unconstrained Portfolio (independent sizing) vs our newly designed
Portfolio Risk-Constrained Portfolio (VaR budgeting, correlation scale-down, sector caps).

Saves a diagnostics JSON report to data/portfolio_diagnostics_report.json.
Renders beautiful terminal correlation heatmaps and portfolio dashboards.
"""

import os
import json
import numpy as np
import pandas as pd
import warnings
from datetime import datetime
from typing import Dict, List, Tuple

# Import Portfolio components
from config import Config
from core.correlation_engine import CorrelationEngine
from core.exposure_tracker import ExposureTracker
from core.portfolio_manager import PortfolioManager

# Gracefully silence pandas warnings
warnings.filterwarnings("ignore")


def generate_correlated_portfolio_data(
    btc_df: pd.DataFrame, 
    n_samples: int = 1000
) -> Dict[str, pd.DataFrame]:
    """
    Synthesizes ETH, SOL, XRP, and BNB prices anchored on actual historical BTC data,
    using a correlated geometric Brownian motion process to match real crypto market correlations.
    """
    print("📈 Generating high-fidelity multi-asset pricing models anchored on BTC historical cache...")
    
    # Extract BTC close and calculate returns
    btc_close = btc_df["Close"].tail(n_samples).values
    n = len(btc_close)
    
    # Historical parameters
    btc_returns = np.diff(btc_close) / btc_close[:-1]
    btc_mu = np.mean(btc_returns)
    btc_sigma = np.std(btc_returns)
    
    # Establish target correlation matrix with BTC
    # W represents the Cholesky factor matrix to generate correlated returns
    # Asset Order: BTC, ETH, SOL, XRP, BNB
    corr_target = np.array([
        [1.00, 0.82, 0.71, 0.61, 0.68],
        [0.82, 1.00, 0.75, 0.64, 0.70],
        [0.71, 0.75, 1.00, 0.58, 0.65],
        [0.61, 0.64, 0.58, 1.00, 0.59],
        [0.68, 0.70, 0.65, 0.59, 1.00]
    ])
    
    # Cholesky decomposition: Corr = L * L^T
    L = np.linalg.cholesky(corr_target)
    
    # Volatilities relative to BTC
    vol_multipliers = {
        "BTC": 1.0,
        "ETH": 1.15,  # Slightly higher volatility
        "SOL": 1.60,  # L1 Alt high volatility
        "XRP": 1.45,  # DeFi volatile payment
        "BNB": 0.90   # Utility slightly lower volatility
    }
    
    portfolio_prices = {}
    
    # Asset price generation loop
    assets = ["BTC", "ETH", "SOL", "XRP", "BNB"]
    generated_returns = np.zeros((len(assets), n - 1))
    
    # Anchor returns for BTC
    generated_returns[0, :] = btc_returns
    
    # Generate correlated random returns for other assets
    for i in range(1, len(assets)):
        # Generate independent standard normals
        z = np.random.randn(n - 1)
        # Apply Cholesky weights to correlate with BTC return stream
        # returns_i = mu_i * dt + sigma_i * (L_i,0 * Z_0 + L_i,1 * Z_1 + ...)
        correlated_z = np.dot(L[i, :i+1], np.append(generated_returns[:i, :], z.reshape(1, -1), axis=0)[:, :])
        
        # Scale to asset specific volatility
        asset_name = assets[i]
        asset_sigma = btc_sigma * vol_multipliers[asset_name]
        asset_mu = btc_mu * 1.05  # slight drift variation
        
        generated_returns[i, :] = asset_mu + asset_sigma * correlated_z[i]
    
    # Reconstruct prices from return series
    base_prices = {
        "BTC": btc_close[0],
        "ETH": btc_close[0] / 15.0,
        "SOL": btc_close[0] / 300.0,
        "XRP": 0.65,
        "BNB": btc_close[0] / 100.0
    }
    
    # Datetime index matching
    dt_index = btc_df.index[-n:]
    
    for idx, asset in enumerate(assets):
        price_series = np.zeros(n)
        price_series[0] = base_prices[asset]
        for t in range(1, n):
            price_series[t] = price_series[t-1] * (1.0 + generated_returns[idx, t-1])
        
        # Build DataFrame with basic Technical Indicators
        df = pd.DataFrame(index=dt_index)
        df["Close"] = price_series
        df["Open"] = price_series * (1.0 + np.random.randn(n)*0.001)
        df["High"] = df[["Open", "Close"]].max(axis=1) * (1.0 + np.abs(np.random.randn(n))*0.003)
        df["Low"] = df[["Open", "Close"]].min(axis=1) * (1.0 - np.abs(np.random.randn(n))*0.003)
        df["Volume"] = np.random.uniform(1000, 50000, size=n)
        
        # Add basic indicators needed for the DecisionEngine / features
        df["rsi_14"] = 50 + 15 * np.sin(np.linspace(0, 10, n)) + np.random.randn(n)*5
        df["rsi_14"] = np.clip(df["rsi_14"], 10, 90)
        df["ema_200"] = df["Close"].rolling(200).mean().fillna(df["Close"])
        df["ema_400"] = df["Close"].rolling(400).mean().fillna(df["Close"])
        df["atr_pct"] = np.random.uniform(0.1, 0.8, size=n)
        df["market_regime"] = np.random.choice(["TRENDING", "RANGING"], size=n)
        df["cdl_engulfing"] = np.random.choice([0, 100, -100], p=[0.8, 0.1, 0.1], size=n)
        df["volume_bias"] = np.random.choice(["BULLISH", "BEARISH", "NEUTRAL"], size=n)
        df["dist_to_psy_level"] = np.random.uniform(0.01, 0.99, size=n)
        
        portfolio_prices[asset] = df
        
    return portfolio_prices


def simulate_portfolio(
    portfolio_prices: Dict[str, pd.DataFrame],
    constrained: bool = True
) -> dict:
    """Simulates a multi-asset portfolio walk-forward backtest."""
    assets = ["BTC", "ETH", "SOL", "XRP", "BNB"]
    initial_balance = 10000.0
    balance = initial_balance
    
    # Initialize engines
    corr_engine = CorrelationEngine(assets)
    portfolio_mgr = PortfolioManager(
        assets=assets,
        var_confidence=0.95,
        var_limit_pct=0.05,        # 5% VaR cap
        max_aggregate_leverage=5.0 # 5x aggregate leverage ceiling
    )
    
    # State tracking
    positions = {asset: {"status": "INACTIVE", "size": 0.0, "side": None, "entry": 0.0} for asset in assets}
    equity_curve = [initial_balance]
    peak_balance = initial_balance
    max_drawdown = 0.0
    
    # Diagnostic counts
    metrics = {
        "trades_attempted": 0,
        "trades_executed": 0,
        "leverage_violations_gated": 0,
        "var_violations_gated": 0,
        "sector_violations_gated": 0,  # backward-compatible: true full sector blocks only
        "sector_reductions": 0,
        "sector_blocks": 0,
        "correlation_reductions": 0,
        "scaled_trades": 0,
        "total_pnl": 0.0
    }
    
    n_candles = len(portfolio_prices["BTC"])
    
    # Chronological simulation loop
    for t in range(50, n_candles):
        # Update rolling price feeds in correlation engine
        current_prices = {}
        for asset in assets:
            df = portfolio_prices[asset]
            # Update price slice history
            corr_engine.update_prices(
                asset=asset,
                datetime_series=df.index[:t+1],
                close_series=df["Close"].iloc[:t+1]
            )
            current_prices[asset] = float(df["Close"].iloc[t])
            
        # Update active positions checks (close trade or check stop-loss/take-profits)
        for asset in assets:
            pos = positions[asset]
            if pos["status"] == "ACTIVE":
                df = portfolio_prices[asset]
                current_price = current_prices[asset]
                entry = pos["entry"]
                side = pos["side"]
                size = pos["size"]
                
                # Check outcome based on close price
                # Hold period of 5 candles proxy
                hold_time = t - pos["entry_t"]
                
                # SL/TP simulation
                # Buy position
                if side == "BUY":
                    tp = entry * 1.04
                    sl = entry * 0.98
                    hit_tp = current_price >= tp
                    hit_sl = current_price <= sl
                else: # Sell position
                    tp = entry * 0.96
                    sl = entry * 1.02
                    hit_tp = current_price <= tp
                    hit_sl = current_price >= sl
                    
                if hit_tp or hit_sl or hold_time >= 6:
                    # Resolve position
                    if hit_tp:
                        trade_pnl = size * entry * 0.04
                    elif hit_sl:
                        trade_pnl = -size * entry * 0.02
                    else: # Time exit
                        ret = (current_price - entry) / entry if side == "BUY" else (entry - current_price) / entry
                        trade_pnl = size * entry * ret
                        
                    balance += trade_pnl
                    positions[asset] = {"status": "INACTIVE", "size": 0.0, "side": None, "entry": 0.0}
                    
        # Check for new signals
        # Simulates a technical breakout trigger with ~8% trigger probability per candle
        for asset in assets:
            pos = positions[asset]
            if pos["status"] == "INACTIVE":
                df = portfolio_prices[asset]
                close = current_prices[asset]
                
                # Generate signal based on indicators
                # Strong RSI or engulfing candlestick trigger
                rsi = df["rsi_14"].iloc[t]
                eng = df["cdl_engulfing"].iloc[t]
                
                signal_side = None
                if rsi < 28 or eng == 100:
                    signal_side = "BUY"
                elif rsi > 72 or eng == -100:
                    signal_side = "SELL"
                    
                if signal_side:
                    metrics["trades_attempted"] += 1
                    
                    # Size trade via standard Kelly sizing (15% default balance risk -> 1.5x leverage)
                    proposed_risk = 0.15
                    # standard leverage: 10x
                    leverage = 10.0
                    proposed_size = (balance * proposed_risk * leverage) / close
                    proposed_notional = proposed_size * close
                    
                    # Calculate rolling returns & correlation matrix
                    returns_df = corr_engine.calculate_returns()
                    corr_matrix = corr_engine.get_correlation_matrix(returns_df)
                    
                    # Sizing / Routing Evaluation
                    if constrained:
                        is_allowed, size_multiplier, warnings_list = portfolio_mgr.evaluate_proposed_trade(
                            asset=asset,
                            side=signal_side,
                            proposed_notional=proposed_notional,
                            active_positions=positions,
                            current_prices=current_prices,
                            corr_matrix=corr_matrix,
                            returns_df=returns_df,
                            balance=balance
                        )
                        
                        # Process compliance outputs. Keep full blocks separate from
                        # size reductions; otherwise diagnostics overstate hard gating.
                        trade_was_scaled = size_multiplier < 0.999
                        for w in warnings_list:
                            w_lower = w.lower()
                            if "leverage" in w_lower:
                                metrics["leverage_violations_gated"] += 1
                            elif "var budget" in w_lower:
                                metrics["var_violations_gated"] += 1
                            elif "sector" in w_lower:
                                if size_multiplier == 0.0:
                                    metrics["sector_blocks"] += 1
                                    metrics["sector_violations_gated"] += 1
                                else:
                                    metrics["sector_reductions"] += 1
                            elif "correlation" in w_lower:
                                metrics["correlation_reductions"] += 1

                        if trade_was_scaled:
                            metrics["scaled_trades"] += 1

                        if not is_allowed and size_multiplier == 0.0:
                            # Blocked entirely by portfolio rules
                            continue

                        # Scale down trade size based on portfolio recommendation
                        final_notional = proposed_notional * size_multiplier
                        proposed_size = final_notional / close
                    
                    # Execute position
                    if proposed_size > 0.0:
                        positions[asset] = {
                            "status": "ACTIVE",
                            "size": proposed_size,
                            "side": signal_side,
                            "entry": close,
                            "entry_t": t
                        }
                        metrics["trades_executed"] += 1
                        
        equity_curve.append(balance)
        if balance > peak_balance:
            peak_balance = balance
        dd = (peak_balance - balance) / peak_balance * 100.0
        if dd > max_drawdown:
            max_drawdown = dd
            
    metrics["equity_curve"] = equity_curve
    metrics["final_balance"] = balance
    metrics["net_pnl_pct"] = (balance - initial_balance) / initial_balance * 100.0
    metrics["max_drawdown"] = max_drawdown
    
    # Calculate Sharpe ratio of equity returns
    eq_returns = np.diff(equity_curve) / equity_curve[:-1]
    metrics["sharpe"] = (float(np.mean(eq_returns) / np.std(eq_returns)) * np.sqrt(252)) if np.std(eq_returns) > 0 else 0.0
    
    return metrics


def main():
    print("=" * 80)
    print("      MULTI-ASSET PORTFOLIO ENGINEERING SYSTEM — SIMULATION RUNNER     ")
    print("=" * 80)
    
    # Load actual historical BTC data from parquet to act as pricing anchor
    btc_df = None
    btc_path = Config.AI_FEATURES_PATH
    if os.path.exists(btc_path):
        try:
            import polars as pl
            btc_df = pl.read_parquet(btc_path).to_pandas()
            # If the features parquet doesn't have technical prices, load cache
            cache_path = os.path.join("data", "btc_15m_cache.parquet")
            if os.path.exists(cache_path):
                btc_df = pl.read_parquet(cache_path).to_pandas()
            print(f"📂 Found historical price anchor: {len(btc_df)} BTC candles.")
        except Exception as e:
            print(f"⚠️ Price loader warning: {e}")
            
    if btc_df is None or len(btc_df) < 500:
        # Fallback synthetic anchor
        print("🔧 Generating synthetic BTC pricing anchor...")
        np.random.seed(42)
        n_samples = 1200
        dt_idx = pd.date_range(start="2026-01-01", periods=n_samples, freq="15min")
        btc_df = pd.DataFrame(index=dt_idx)
        btc_df["Close"] = 65000.0 + np.cumsum(np.random.randn(n_samples) * 150.0)
        
    # ── 1. PORTFOLIO DATA GENERATION ──────────────────────────────────────────
    portfolio_prices = generate_correlated_portfolio_data(btc_df, n_samples=1000)
    assets = ["BTC", "ETH", "SOL", "XRP", "BNB"]
    
    # Create aligned correlation matrices for visual outputs
    corr_engine = CorrelationEngine(assets)
    for asset in assets:
        df = portfolio_prices[asset]
        corr_engine.update_prices(asset, df.index, df["Close"])
    
    returns_df = corr_engine.calculate_returns()
    corr_matrix = corr_engine.get_correlation_matrix(returns_df)
    clustering = corr_engine.get_volatility_clustering(returns_df)
    
    # ── 2. RUN BENCHMARK SIMULATION loops ──────────────────────────────────────
    print("\n⏳ Simulating Unconstrained Portfolio Performance (Independent Sizing)...")
    unconstrained_results = simulate_portfolio(portfolio_prices, constrained=False)
    
    print("⏳ Simulating Risk-Constrained Portfolio Performance (Portfolio Manager Gating)...")
    constrained_results = simulate_portfolio(portfolio_prices, constrained=True)
    
    # ── 3. RENDER BEAUTIFUL HEATMAP ───────────────────────────────────────────
    print("\n" + "="*80)
    print(f"📊 \033[1m\033[96mROLLING CORRELATION HEATMAP (Crypto Asset Returns)\033[0m")
    print("="*80)
    print(corr_engine.render_ascii_heatmap(corr_matrix))
    print(f"Volatility Clustering diagnostics (ARCH):")
    for a in assets:
        c_val = clustering.get(a, 1.0)
        status = "\033[91mHIGH (Contagion Alert)\033[0m" if c_val > 1.25 else "\033[92mNORMAL\033[0m"
        print(f"  • {a:<4}: Cluster Ratio: {c_val:.2f} | Status: {status}")
    print("="*80)

    # ── 4. RENDER DASHBOARD & PERFORMANCE TABLES ──────────────────────────────
    print(f"\n📊 \033[1m\033[96mPORTFOLIO SYSTEM EVALUATION & BENCHMARK REPORT\033[0m")
    print("-" * 80)
    print(f"  Metric                      Unconstrained       Constrained       Advantage")
    print(f"  ----------------------------------------------------------------------------")
    print(f"  Total Attempts              {unconstrained_results['trades_attempted']:<19} {constrained_results['trades_attempted']:<17} --")
    print(f"  Executed Trades             {unconstrained_results['trades_executed']:<19} {constrained_results['trades_executed']:<17} Blocked {unconstrained_results['trades_executed'] - constrained_results['trades_executed']} trades")
    
    pnl_un = unconstrained_results['net_pnl_pct']
    pnl_co = constrained_results['net_pnl_pct']
    print(f"  Net Simulated PnL (%)       {pnl_un:+.2f}%             {pnl_co:+.2f}%            {pnl_co - pnl_un:+.2f}%")
    
    sharpe_un = unconstrained_results['sharpe']
    sharpe_co = constrained_results['sharpe']
    print(f"  Portfolio Sharpe Ratio      {sharpe_un:.3f}              {sharpe_co:.3f}               {sharpe_co - sharpe_un:+.3f}")
    
    dd_un = unconstrained_results['max_drawdown']
    dd_co = constrained_results['max_drawdown']
    print(f"  Portfolio Max Drawdown      {dd_un:.2f}%              {dd_co:.2f}%              {dd_un - dd_co:+.2f}% reduction")
    print("-" * 80)
    
    # ── 5. COMPLIANCE GATING DETAILS ──────────────────────────────────────────
    print(f"\n🎯 \033[1m\033[93mPORTFOLIO MANAGER COMPLIANCE GATING ACTIVITY:\033[0m")
    print(f"  • Leverage Limit Breaches Blocked/Scaled: {constrained_results['leverage_violations_gated']}")
    print(f"  • Value at Risk (VaR) Limit Gates       : {constrained_results['var_violations_gated']}")
    print(f"  • Sector Overconcentration Blocks       : {constrained_results['sector_blocks']}")
    print(f"  • Sector Exposure Size Reductions       : {constrained_results['sector_reductions']}")
    print(f"  • Correlated Asset Exposures Scaled     : {constrained_results['correlation_reductions']}")
    print(f"  • Total Size-Scaled Trades              : {constrained_results['scaled_trades']}")
    print("-" * 80)
    
    # ── 6. EXPORT REPORT TO JSON ──────────────────────────────────────────────
    report_json = {
        "timestamp": datetime.now().isoformat(),
        "assets_supported": assets,
        "unconstrained_benchmark": {
            "trades_attempted": unconstrained_results["trades_attempted"],
            "trades_executed": unconstrained_results["trades_executed"],
            "net_pnl_pct": unconstrained_results["net_pnl_pct"],
            "max_drawdown_pct": unconstrained_results["max_drawdown"],
            "sharpe_ratio": unconstrained_results["sharpe"]
        },
        "constrained_portfolio": {
            "trades_attempted": constrained_results["trades_attempted"],
            "trades_executed": constrained_results["trades_executed"],
            "net_pnl_pct": constrained_results["net_pnl_pct"],
            "max_drawdown_pct": constrained_results["max_drawdown"],
            "sharpe_ratio": constrained_results["sharpe"],
            "leverage_violations_gated": constrained_results["leverage_violations_gated"],
            "var_violations_gated": constrained_results["var_violations_gated"],
            "sector_violations_gated": constrained_results["sector_violations_gated"],
            "sector_blocks": constrained_results["sector_blocks"],
            "sector_reductions": constrained_results["sector_reductions"],
            "correlation_reductions": constrained_results["correlation_reductions"],
            "scaled_trades": constrained_results["scaled_trades"]
        },
        "market_correlations": corr_matrix.to_dict(),
        "volatility_clustering": clustering
    }
    
    report_path = os.path.join("data", "portfolio_diagnostics_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report_json, f, indent=4)
    print(f"\n✅ Portfolio Diagnostics report exported successfully -> {report_path}")
    
    # ── 7. EXPLANATORY QUANT CORNER ───────────────────────────────────────────
    print("\n" + "="*80)
    print(f"🧪 \033[1mPORTFOLIO SYSTEMS ENGINEERING — QUANT CORNER\033[0m")
    print("="*80)
    print("""
  1. WHY PORTFOLIO-LEVEL RISK MATTERS MORE THAN INDIVIDUAL TRADES:
     - Individual trades represent localized idiosyncratic edge. However, when assets
       experience massive co-movements (systemic shock), individual edges are wiped out.
     - A portfolio with 5 long positions in assets with > 0.80 correlation does not
       have 5 diversified bets; it has 1 highly leveraged bet on the market beta.
     - Portfolio-level risk management (VaR budgets and correlation scaling) ensures
       the total capital remains bounded against systematic ruin.

  2. HOW INSTITUTIONAL SYSTEMS MANAGE CORRELATED EXPOSURES:
     - Quants utilize dynamic covariance-based risk budgeting. Rather than static 2% sizers,
       positions are sized via Risk-Parity (inverse-volatility scaling) so each asset
       contributes equally to total portfolio risk.
     - Systems establish hard aggregate leverage boundaries (e.g. 5x) and sector allocation
       ceilings (e.g. L1 majors vs L1 alts) to isolate contagion.
     - Correlation matrices are monitored daily. During volatility clusters, matrices
       frequently 'converge to 1'. Real-time portfolio systems dynamically scale down
       correlation-exposed trades to preemptively reduce systemic beta.
    """)
    print("="*80)


if __name__ == "__main__":
    main()
