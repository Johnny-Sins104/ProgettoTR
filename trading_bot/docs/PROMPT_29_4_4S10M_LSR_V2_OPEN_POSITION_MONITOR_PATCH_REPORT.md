# PROMPT 29.4.4s-10m — LSR-v2 open position monitor / SL-TP tracking audit

## Scope
Adds an audit-only monitor for the first supervised paper-only LSR-v2 position. The monitor reads `paper_state.json`, `paper_status.json`, `paper_events.jsonl`, and the LSR-v2 lifecycle/execution artifacts, then reports current price, unrealized PnL, R multiple, stop/target distances, position age, and SL/TP diagnostic flags.

## Files
- `trading_bot/core/lsr_v2_open_position_monitor.py`
- `trading_bot/run_lsr_v2_open_position_monitor.py`
- `trading_bot/tests/test_lsr_v2_open_position_monitor.py`
- `trading_bot/docs/PROMPT_29_4_4S10M_LSR_V2_OPEN_POSITION_MONITOR_PATCH_REPORT.md`

## Outputs
- `data/lsr_v2_open_position_monitor_report.json`
- `data/lsr_v2_open_position_monitor.jsonl`

## Decisions
- `LSR_V2_OPEN_POSITION_MONITOR_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND`
- `KEEP_DIAGNOSTIC_LSR_V2_MONITOR_STATE_INCONSISTENT`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_REQUIRED_DIAGNOSTIC`
- `REJECT_LSR_V2_OPEN_POSITION_MONITOR_SAFETY_FAILED`

## Safety invariants
- No new order.
- No new position.
- No broker submit.
- No automatic close.
- No automatic re-entry.
- No live execution.
- No testnet execution.
- No exchange broker.
- No paper state mutation.

## Validation
Sandbox validation passed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_open_position_monitor.py
5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_open_position_monitor.py trading_bot/tests/test_lsr_v2_paper_position_lifecycle.py trading_bot/tests/test_lsr_v2_paper_status_reconciliation.py trading_bot/tests/test_lsr_v2_supervised_paper_submit_execution.py
20 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_open_position_monitor.py trading_bot/run_lsr_v2_open_position_monitor.py
OK
```

## Notes
The runner returns a warning decision if no open LSR-v2 position is found. It never closes a position even when stop or take-profit diagnostics are triggered; it only emits `close_required_diagnostic=true`.
