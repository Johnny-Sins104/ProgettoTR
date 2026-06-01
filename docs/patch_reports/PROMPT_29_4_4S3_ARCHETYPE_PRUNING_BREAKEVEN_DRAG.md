# Prompt 29.4.4s-3 — Archetype pruning + breakeven drag hardening

## Scope

Diagnostic-only hardening after `29.4.4s-2b`. The patch extends edge strategy discovery with explicit breakeven drag metrics and pruning recommendations.

It does **not**:

- enable live trading;
- enable testnet;
- enable an exchange broker;
- submit paper orders;
- lower thresholds;
- force candidate orders;
- automatically apply pruning to runtime gates.

## Rationale

The post-`29.4.4s-2b` discovery matrix showed no valid multi-window edge strategy. `LIQUIDITY_SWEEP_REVERSAL` was promising but low-sample, while `RANGING_MEAN_REVERSION` had enough trades and persistent negative realized edge. Many of those mean-reversion trades ended as breakevens, but the aggregated R remained negative, showing that breakeven behavior was fee/slippage drag rather than real protection.

## Changes

### `core/edge_strategy_discovery.py`

Adds per-archetype and per-window:

- `win_ratio`;
- `loss_ratio`;
- `breakeven_ratio`;
- `completed_non_win_ratio`;
- `total_breakevens`;
- `breakeven_drag_detected`;
- `breakeven_drag_windows`;
- `breakeven_drag_labels`;
- `prune_recommended`.

Adds report-level objects:

- `pruning_recommendations`;
- `breakeven_drag_summary`.

New diagnostic decision:

- `KEEP_DIAGNOSTIC_ARCHETYPE_PRUNING_REQUIRED`.

Expected current recommendation from the included matrix:

- hard-block candidate: `RANGING_MEAN_REVERSION`;
- watchlist expansion candidate: `LIQUIDITY_SWEEP_REVERSAL`;
- diagnostic-only candidate: `SESSION_MOMENTUM`.

### `run_edge_strategy_discovery.py`

Adds CLI controls:

- `--max-breakeven-drag-ratio`;
- `--max-breakeven-drag-avg-r`;
- `--min-prune-trades`.

### `test_edge_strategy_discovery.py`

Adds a regression test confirming that a high-breakeven, negative-R mean-reversion archetype is recommended for pruning, while a low-sample positive liquidity sweep archetype is not hard-blocked.

## Validation

Sandbox validation passed:

```cmd
python -m compileall -q trading_bot
python trading_bot\test_edge_strategy_discovery.py
python trading_bot\test_signal_risk_correctness_hardening.py
python trading_bot\test_runtime_risk_io_hardening.py
python trading_bot\test_probability_compression_diagnostic.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
```

## Local run

After applying the patch:

```cmd
python -m compileall -q trading_bot
python trading_bot\test_edge_strategy_discovery.py
python trading_bot\run_edge_strategy_discovery.py --windows 10000,12000,15000,18000,20000
```

To regenerate the full matrix:

```cmd
python trading_bot\run_edge_strategy_discovery.py --run-backtests --windows 10000,12000,15000,18000,20000 --balance 100
```

## Interpretation

If the report returns `KEEP_DIAGNOSTIC_ARCHETYPE_PRUNING_REQUIRED`, do not proceed to supervised execution. Review `pruning_recommendations` first. Runtime pruning should be wired only in a later patch after operator review.
