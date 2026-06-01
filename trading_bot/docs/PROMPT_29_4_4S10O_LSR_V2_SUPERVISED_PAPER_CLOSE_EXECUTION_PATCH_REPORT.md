# PROMPT 29.4.4s-10o — LSR-v2 supervised paper close execution / single-position TP close

## Scope

Adds a supervised paper-only close execution boundary for the already-open LSR-v2 paper position that was flagged by the open-position monitor with `close_required_diagnostic=true` / `TAKE_PROFIT_HIT_DIAGNOSTIC`.

The patch closes at most one existing paper position and does not open new orders, re-enter, call live/testnet/exchange brokers, or enable automatic lifecycle actions.

## Added files

- `trading_bot/core/lsr_v2_supervised_paper_close_execution.py`
- `trading_bot/run_lsr_v2_supervised_paper_close_execution.py`
- `trading_bot/tests/test_lsr_v2_supervised_paper_close_execution.py`

## Runtime controls

Close execution is disabled by default and requires all of:

```powershell
$env:LSR_V2_PAPER_CLOSE_ENABLE="1"
$env:LSR_V2_PAPER_CLOSE_CONFIRMATION="I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY"
$env:LSR_V2_PAPER_CLOSE_MAX_POSITIONS="1"
```

## Inputs

- `data/lsr_v2_supervised_paper_close_preflight_report.json`
- `data/lsr_v2_supervised_paper_close_preflight.jsonl`
- `data/lsr_v2_open_position_monitor_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- `data/paper_events.jsonl`

## Outputs

- `data/lsr_v2_supervised_paper_close_execution_report.json`
- `data/lsr_v2_supervised_paper_close_execution.jsonl`
- backups under `data/lsr_v2_paper_close_execution_backups/` before state/status mutation

## Decisions

- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_NOT_ENABLED`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_PREFLIGHT_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND`
- `KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_MAX_POSITION_CAP_BLOCKED`
- `LSR_V2_SINGLE_PAPER_POSITION_CLOSED`
- `REJECT_LSR_V2_CLOSE_EXECUTION_SAFETY_FAILED`

## Safety invariants

- No new order
- No re-entry
- At most one position closed
- Paper-only state/status mutation
- Backup before mutation
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`
- No automatic close loop
- No automatic re-entry

## Validation

Sandbox validation:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_close_execution.py
6 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_close_execution.py trading_bot/tests/test_lsr_v2_supervised_paper_close_preflight.py trading_bot/tests/test_lsr_v2_open_position_monitor.py trading_bot/tests/test_lsr_v2_paper_position_lifecycle.py
22 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_supervised_paper_close_execution.py trading_bot/run_lsr_v2_supervised_paper_close_execution.py
OK
```
