# PROMPT 29.4.4s-10d — LSR-v2 runtime cycle-scoped candidate bridge audit

## Scope

This patch makes the LSR-v2 paper-supervised bridge cycle-scoped in the paper runtime.  The previous bridge report remained useful as a standalone diagnostic artifact, but the once-cycle footer could display historical standalone bridge counts.  This patch adds runtime candidate/bridge audit events generated from the market dataframe of each scanned symbol in the current paper cycle.

## Added

- `core/lsr_v2_runtime_bridge.py`
  - Converts runtime OHLCV dataframes into LSR-v2 detector rows.
  - Emits `LSR_V2_RUNTIME_CANDIDATE_AUDIT` per scanned symbol.
  - Emits cycle-scoped `LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT` events.
  - Writes `data/lsr_v2_runtime_bridge_report.json`.
  - Writes `data/lsr_v2_runtime_bridge_audit.jsonl`.
  - Detects whether the standalone bridge report is stale relative to the current cycle.

## Updated

- `core/paper_engine.py`
  - Integrates the runtime bridge per scanned symbol after market data fetch and before order-path logic.
  - Writes runtime bridge artifacts during performance artifact generation.
  - Stops mirroring historical standalone bridge events into `paper_events.jsonl`; runtime visibility now uses current-cycle events.

- `core/paper_once_console_summary.py`
  - Adds `lsr_v2_runtime_bridge` footer section.
  - Keeps legacy standalone LSR-v2 bridge footer section for comparison.

- `core/paper_once_runner_footer.py`
  - Loads `lsr_v2_runtime_bridge_report.json` for the watchdog fallback footer.
  - Prints explicit missing-report diagnostics when runtime bridge data is unavailable.
  - Force-pins all runtime LSR-v2 order/submission fields to zero in footer presentation.

- `core/lsr_v2_paper_supervised_bridge.py`
  - Accepts `LSR_V2_RUNTIME_CANDIDATE_AUDIT` as a valid candidate source for the fail-closed bridge.

## Safety invariants

- `would_submit=false` always.
- `broker_submit_called=false` always.
- `routing_enabled=false`.
- `execution_enabled=false`.
- `paper_order_submission_enabled=false`.
- `orders_submitted_by_lsr_v2_runtime_bridge=0`.
- `positions_opened_by_lsr_v2_runtime_bridge=0`.
- No live, no testnet, no exchange broker.
- No paper state mutation.
- No threshold lowering.

## Expected once footer fields

```text
lsr_v2_runtime_bridge_decision=...
lsr_v2_runtime_cycle_id=pc_...
lsr_v2_runtime_bridge_events=4
lsr_v2_runtime_candidate_events=4
lsr_v2_runtime_candidate_ready_events=0/1/...
lsr_v2_runtime_would_route_count=0
lsr_v2_runtime_would_submit_count=0
orders_submitted_by_lsr_v2_runtime_bridge=0
positions_opened_by_lsr_v2_runtime_bridge=0
lsr_v2_standalone_bridge_events=...
lsr_v2_bridge_report_cycle_id=...
lsr_v2_bridge_report_stale=true/false
```

## Validation

Sandbox/context validation:

```text
python -m pytest -q \
  trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py \
  trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py \
  trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py \
  trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py
```

Result:

```text
18 passed
```

Compile validation:

```text
python -m compileall -q trading_bot
python -m py_compile \
  trading_bot/core/lsr_v2_runtime_bridge.py \
  trading_bot/core/paper_engine.py \
  trading_bot/core/paper_once_console_summary.py \
  trading_bot/core/paper_once_runner_footer.py
```

Result: OK.

## Operator validation commands

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_runtime_bridge_cycle_scoped.py trading_bot\tests\test_paper_once_runner_footer_lsr_v2.py trading_bot\tests\test_lsr_v2_paper_runtime_bridge_integration.py trading_bot\tests\test_lsr_v2_paper_supervised_bridge.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_paper_supervised_bridge.py --data-dir data
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```
