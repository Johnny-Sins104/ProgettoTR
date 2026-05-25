# Prompt 29.4.4o-1 + 29.4.4p — Paper once console summary + guarded routing bridge

## Scope

Integrated cumulative patch:

- `29.4.4o-1 — Paper once-cycle console completion hotfix`
- `29.4.4p — Guarded paper-only routing bridge / accepted-signal order simulation`

## 29.4.4o-1

Adds a deterministic final console footer for `run_paper_trading.py --once` after the cycle is completed and artifacts are generated.

Expected footer includes:

```text
[PAPER CYCLE COMPLETED]
cycle_id=...
scanned=...
signals=...
orders=...
open_positions=...
errors=...
elapsed_seconds=...
paper_orders_enabled=true/false
paper_unlock_experiment_allowed=true/false
operational_unlock_allowed=false
runtime_audit_events=...
runtime_accepts_diagnostic=...
runtime_rejects=...
[PAPER ONCE RESULT] NO_SIGNAL
```

The formatter is pure and non-invasive. It does not change broker state, gates, risk, orders, or positions.

## 29.4.4p

Adds a fail-closed paper-only routing bridge audit event:

```text
GUARDED_PAPER_ROUTING_BRIDGE_AUDIT
```

For every runtime audit event, the bridge logs:

- `accepted_diagnostic`
- paper operator state
- `would_route`
- `would_submit`
- `blocked_reason` / `blocked_reasons`
- `risk_per_trade_pct=0.0025`
- `max_positions=1`
- live/testnet/exchange broker blocked state
- `orders_submitted_by_bridge=0`

The bridge is simulation-only in this patch. It never submits orders and never opens positions.

## Safety invariants

Unchanged:

```text
operational_unlock_allowed=false
automatic_activation_allowed=false
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
```

## Files added

- `trading_bot/core/paper_once_console_summary.py`
- `trading_bot/core/paper_unlock_routing_bridge.py`
- `trading_bot/run_paper_unlock_routing_bridge.py`
- `trading_bot/test_paper_once_console_summary.py`
- `trading_bot/test_paper_unlock_routing_bridge.py`

## Files modified

- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`

## Validation

Recommended tests:

```cmd
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_guarded_enable.py
python -m py_compile trading_bot\core\paper_once_console_summary.py trading_bot\core\paper_unlock_routing_bridge.py trading_bot\core\paper_engine.py trading_bot\run_paper_trading.py trading_bot\run_paper_unlock_routing_bridge.py
```

## Runtime commands

```cmd
python trading_bot\run_paper_unlock_guarded_enable.py
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
```
