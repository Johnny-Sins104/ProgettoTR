# Prompt 29.4.4s-4 — Apply diagnostic archetype pruning to paper/runtime gates

## Scope

This patch connects the `29.4.4s-3` edge-discovery pruning recommendation to the paper runtime as a diagnostic-first gate.

It does **not** enable live, testnet, exchange broker, supervised execution, or automatic order submission.

## Runtime policy

Default behavior is audit-only:

```text
EDGE_STRATEGY_PRUNING_ENABLED=0
EDGE_STRATEGY_PRUNING_AUDIT_ENABLED=1
EDGE_STRATEGY_BLOCKED_ARCHETYPES=RANGING_MEAN_REVERSION
EDGE_STRATEGY_WATCHLIST_ARCHETYPES=LIQUIDITY_SWEEP_REVERSAL
```

When audit is enabled, each detected signal emits:

```text
EDGE_STRATEGY_ARCHETYPE_PRUNING_AUDIT
```

If and only if the operator explicitly sets `EDGE_STRATEGY_PRUNING_ENABLED=1`, the gate blocks detected signals whose archetype is in `EDGE_STRATEGY_BLOCKED_ARCHETYPES`.

## Files

- `trading_bot/core/edge_strategy_runtime_pruning.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/config.py`
- `trading_bot/run_edge_strategy_runtime_pruning.py`
- `trading_bot/test_edge_strategy_runtime_pruning.py`

## Safety

- No live/testnet/exchange broker changes.
- No order submission by the pruning module.
- No position opening by the pruning module.
- Default is diagnostic-only.
- Blocking requires explicit operator opt-in.

## Validation

Sandbox validation passed:

```text
python -m compileall -q trading_bot
python trading_bot\test_edge_strategy_runtime_pruning.py
python trading_bot\test_edge_strategy_discovery.py
python trading_bot\test_signal_risk_correctness_hardening.py
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

## Local validation commands

```cmd
python -m compileall -q trading_bot
python trading_bot\test_edge_strategy_runtime_pruning.py
python trading_bot\run_edge_strategy_runtime_pruning.py
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_edge_strategy_runtime_pruning.py
```

To test active blocking in a controlled once-cycle only:

```cmd
set EDGE_STRATEGY_PRUNING_ENABLED=1
set EDGE_STRATEGY_BLOCKED_ARCHETYPES=RANGING_MEAN_REVERSION
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_edge_strategy_runtime_pruning.py
set EDGE_STRATEGY_PRUNING_ENABLED=0
```
