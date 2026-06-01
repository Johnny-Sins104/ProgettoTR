# PROMPT 29.4.4s-10ac — LSR-v2 second supervised paper close execution / single-position TP close

## Scope

This patch adds the second-trade-specific supervised paper close execution boundary for the LSR-v2 paper-only workflow.
It closes at most one already-open second LSR-v2 paper position only when the second close preflight has produced a close-required diagnostic and the operator supplies the dedicated confirmation.

## Added files

- `trading_bot/core/lsr_v2_second_trade_close_execution.py`
- `trading_bot/run_lsr_v2_second_trade_close_execution.py`
- `trading_bot/tests/test_lsr_v2_second_trade_close_execution.py`

## Inputs

- `data/lsr_v2_second_trade_close_preflight_report.json`
- `data/lsr_v2_second_trade_close_preflight.jsonl`
- `data/lsr_v2_second_open_position_monitor_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- `data/paper_events.jsonl`

## Outputs

- `data/lsr_v2_second_trade_close_execution_report.json`
- `data/lsr_v2_second_trade_close_execution.jsonl`
- `data/lsr_v2_second_trade_close_execution_backups/`

## Operator controls

Execution requires all of the following:

```powershell
$env:LSR_V2_SECOND_TRADE_CLOSE_ENABLE="1"
$env:LSR_V2_SECOND_TRADE_CLOSE_CONFIRMATION="I_UNDERSTAND_CLOSE_SECOND_PAPER_POSITION_ONLY"
$env:LSR_V2_SECOND_TRADE_CLOSE_MAX_POSITIONS="1"
```

Default mode is non-mutating and returns `KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSE_NOT_ENABLED`.

## Safety invariants

- No new order.
- No new position.
- No re-entry.
- Maximum one position closed.
- No live broker.
- No testnet broker.
- No exchange broker.
- `operational_unlock_allowed=false`.
- Backup is created before mutating `paper_state.json` or `paper_status.json`.

## Expected successful decision

`LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED`

Expected successful counters:

```json
{
  "positions_closed_by_second_trade_close_execution": 1,
  "orders_submitted_by_second_trade_close_execution": 0,
  "positions_opened_by_second_trade_close_execution": 0,
  "open_second_lsr_v2_positions_after": 0,
  "paper_status_open_positions_after": 0,
  "broker_close_called": true
}
```

## Sandbox validation

- `python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_close_execution.py` → 6 passed
- `python -m compileall -q trading_bot` → OK
- `python -m py_compile trading_bot/core/lsr_v2_second_trade_close_execution.py trading_bot/run_lsr_v2_second_trade_close_execution.py` → OK
