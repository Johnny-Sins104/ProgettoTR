# PROMPT 29.4.4s-10l — LSR-v2 paper position lifecycle audit / first order monitoring

## Scope
Adds a diagnostic-only lifecycle audit for the first supervised LSR-v2 paper-only order executed by 29.4.4s-10k.

The patch reads active paper artifacts and verifies that the submitted LSR-v2 paper order is visible in paper state/status as a monitorable position.

## Added files

- `trading_bot/core/lsr_v2_paper_position_lifecycle.py`
- `trading_bot/run_lsr_v2_paper_position_lifecycle.py`
- `trading_bot/tests/test_lsr_v2_paper_position_lifecycle.py`

## Output files

- `data/lsr_v2_paper_position_lifecycle_report.json`
- `data/lsr_v2_paper_position_lifecycle.jsonl`

## Inputs

- `data/paper_state.json`
- `data/paper_status.json`
- `data/paper_events.jsonl`
- `data/lsr_v2_supervised_paper_submit_execution_report.json`
- `data/lsr_v2_supervised_paper_submit_execution.jsonl`

## Decisions

- `LSR_V2_PAPER_POSITION_LIFECYCLE_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND`
- `KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_OPEN_MONITORING`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED`
- `REJECT_LSR_V2_POSITION_LIFECYCLE_SAFETY_FAILED`

## Safety invariants

The lifecycle audit does not submit orders, open positions, close positions, re-enter, or call brokers. It only reads state and writes diagnostic reports.

Hard safety fields remain:

- `orders_submitted_by_lifecycle_audit=0`
- `positions_opened_by_lifecycle_audit=0`
- `broker_submit_called_by_lifecycle_audit=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`
- `automatic_close_enabled=false`
- `automatic_reentry_enabled=false`

## Validation

Sandbox validation passed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_paper_position_lifecycle.py
# 5 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_paper_position_lifecycle.py trading_bot/run_lsr_v2_paper_position_lifecycle.py
# OK
```

## Local validation command

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_paper_position_lifecycle.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_paper_position_lifecycle.py --data-dir data
```
