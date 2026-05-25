# Prompt 29.4.4o-2 — Paper once console flush hotfix

## Scope

Micro-patch on top of `29.4.4o-1 + 29.4.4p`.

This patch only hardens operator-console delivery for:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

It does not change strategy logic, gates, risk, broker routing, paper unlock behavior, runtime audit, or routing bridge semantics.

## Problem

A `CYCLE_COMPLETED` event and `GUARDED_PAPER_ROUTING_BRIDGE_AUDIT` events can be written correctly to `data\paper_events.jsonl`, while the final `[PAPER CYCLE COMPLETED]` footer is not visible in the Windows console, especially if stdout is not flushed before process shutdown or operator interruption.

## Changes

### `trading_bot/core/paper_once_console_summary.py`

- Updated prompt marker to `29.4.4o-2`.
- Keeps deterministic summary generation unchanged.
- Adds explicit `stream` support for tests and future redirection.
- Prints each footer line with `flush=True` by default.
- Performs an explicit final `stream.flush()`.

### `trading_bot/core/paper_engine.py`

- Adds `_last_completed_cycle_summary` memory for the latest completed `--once` cycle.
- Adds `_paper_once_console_summary_printed` guard to prevent duplicate footers.
- Stores the completed cycle summary immediately after `CYCLE_COMPLETED` emission.
- Prints startup banner, cycle summary, monitor lines, and shutdown lines with `flush=True`.
- Adds a final `--once` fallback guard in `run().finally`: if the cycle completed but the footer was not printed yet, it prints the footer once using the already-generated artifacts.

### `trading_bot/test_paper_once_console_summary.py`

- Adds a flush-tracking stream test proving the footer writes and flushes.

## Safety invariants

Unchanged:

```text
operational_unlock_allowed=false
automatic_activation_allowed=false
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
orders_submitted=0 unless existing paper engine would submit independently
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
risk_per_trade_pct unchanged
max_positions unchanged
```

## Expected console behavior

At the end of a completed `--once` run, the operator console should show:

```text
[PAPER CYCLE COMPLETED]
cycle_id=...
scanned=...
signals=...
orders=...
open_positions=...
errors=...
elapsed_seconds=...
paper_orders_enabled=...
paper_unlock_experiment_allowed=...
operational_unlock_allowed=false
runtime_audit_events=...
runtime_accepts_diagnostic=...
runtime_rejects=...
routing_bridge_events=...
would_route_count=...
would_submit_count=...
orders_submitted_by_bridge=...
[PAPER ONCE RESULT] NO_SIGNAL
```

## Validation

Recommended tests:

```cmd
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_guarded_enable.py
python -m py_compile trading_bot\core\paper_once_console_summary.py trading_bot\core\paper_engine.py trading_bot\run_paper_trading.py
```

## Operator verification

Run without pressing `CTRL+C`:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Then verify audits:

```cmd
python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
```
