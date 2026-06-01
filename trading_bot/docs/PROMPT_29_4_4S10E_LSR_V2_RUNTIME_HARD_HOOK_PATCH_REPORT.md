# PROMPT 29.4.4s-10e — LSR-v2 runtime bridge hard-hook + footer event-log fallback

## Scope

Patch visibility/audit-only to complete the cycle-scoped LSR-v2 runtime bridge introduced in 29.4.4s-10d.

The previous 10d integration was safe but the `--once` watchdog footer could still show:

- `KEEP_DIAGNOSTIC_LSR_V2_RUNTIME_BRIDGE_REPORT_MISSING`
- `lsr_v2_runtime_bridge_events=0`
- empty `lsr_v2_runtime_cycle_id`

when the hard-exit footer printed before the normal JSON report was available.

## Changes

- `paper_once_runner_footer.py`
  - Bumps prompt marker to `29.4.4s-10e`.
  - Adds event-log primary fallback for `LSR_V2_RUNTIME_CANDIDATE_AUDIT` and runtime-scoped `LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT`.
  - Counts runtime LSR-v2 events by current `cycle_id` directly from `paper_events.jsonl`.
  - Uses `lsr_v2_runtime_bridge_report.json` only as secondary fallback.
  - Force-pins all LSR-v2 runtime submission/order/position fields to zero.

- `paper_engine.py`
  - Bumps prompt marker to `29.4.4s-10e`.
  - Writes `lsr_v2_runtime_bridge_report.json` incrementally after each symbol-level LSR-v2 runtime bridge emission.
  - Keeps event emission fail-closed and audit-only.

- `paper_once_console_summary.py`
  - Bumps prompt marker to `29.4.4s-10e`.

- `lsr_v2_runtime_bridge.py`
  - Bumps prompt marker to `29.4.4s-10e`.

- Tests
  - Adds regression coverage for watchdog footer counting cycle-scoped runtime LSR-v2 events directly from `paper_events.jsonl`, including hostile/malformed nonzero submission/order counters that must be displayed as zero.

## Safety invariants

The patch does not enable execution:

- `would_submit=false` is preserved.
- `broker_submit_called=false` is preserved.
- `routing_enabled=false` is preserved.
- `execution_enabled=false` is preserved.
- `paper_order_submission_enabled=false` is preserved.
- `orders_submitted_by_lsr_v2_runtime_bridge=0` is preserved.
- `positions_opened_by_lsr_v2_runtime_bridge=0` is preserved.
- No live/testnet/exchange broker path is introduced.
- No paper state mutation is introduced.

## Validation

Sandbox validation on minimal context:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py trading_bot/tests/test_liquidity_sweep_reversal_v2.py
26 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_runtime_bridge.py trading_bot/core/paper_engine.py trading_bot/core/paper_once_runner_footer.py trading_bot/core/paper_once_console_summary.py
OK
```

`test_lsr_v2_promotion_gate.py` was not rerun in the minimal sandbox because the uploaded s-10e context intentionally omitted the full selected-overlay validation module needed by that historical test. It remains part of the full project and should be run locally if available.

## Expected local footer after paper once

```text
prompt=29.4.4s-10e
lsr_v2_runtime_bridge_decision=LSR_V2_RUNTIME_CYCLE_BRIDGE_READY_DIAGNOSTIC
lsr_v2_runtime_cycle_id=pc_...
lsr_v2_runtime_bridge_events=4
lsr_v2_runtime_candidate_events=4
lsr_v2_runtime_would_submit_count=0
orders_submitted_by_lsr_v2_runtime_bridge=0
positions_opened_by_lsr_v2_runtime_bridge=0
```
