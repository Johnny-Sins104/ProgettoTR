# Prompt 29.4.4s-10as — LSR-v2 third supervised paper close execution

## Scope

Adds the third-trade supervised paper-only close execution boundary for the LSR-v2 third paper position opened by `29.4.4s-10ao`, monitored by `29.4.4s-10aq`, and prepared by `29.4.4s-10ar`.

The patch is execution-capable only for the paper state layer and is disabled by default. It closes exactly one matching third LSR-v2 paper position only when the close preflight reports `would_prepare_close=true` / `close_required_diagnostic=true` and the operator explicitly arms the close with the required confirmation phrase.

## Files

- `trading_bot/core/lsr_v2_third_trade_close_execution.py`
- `trading_bot/run_lsr_v2_third_trade_close_execution.py`
- `trading_bot/tests/test_lsr_v2_third_trade_close_execution.py`
- `trading_bot/docs/PROMPT_29_4_4S10AS_THIRD_SUPERVISED_PAPER_CLOSE_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4S10AS_MANIFEST.txt`

## Operator controls

Default state:

```text
LSR_V2_THIRD_TRADE_CLOSE_ENABLE unset/0
LSR_V2_THIRD_TRADE_CLOSE_CONFIRMATION unset
LSR_V2_THIRD_TRADE_CLOSE_MAX_POSITIONS defaults to 1
```

Execution arm:

```text
LSR_V2_THIRD_TRADE_CLOSE_ENABLE=1
LSR_V2_THIRD_TRADE_CLOSE_CONFIRMATION=I_UNDERSTAND_CLOSE_THIRD_PAPER_POSITION_ONLY
LSR_V2_THIRD_TRADE_CLOSE_MAX_POSITIONS=1
```

## Safety contract

- Paper-only state close.
- No live broker.
- No testnet broker.
- No exchange broker.
- No new order creation.
- No submit path.
- No re-entry.
- Maximum one matching third LSR-v2 paper position closed.
- Default disabled unless explicitly armed by operator env and confirmation.
- Backs up `paper_state.json` and `paper_status.json` before any close mutation.

## Reports

Writes:

- `data/lsr_v2_third_trade_close_execution_report.json`
- `data/lsr_v2_third_trade_close_execution.jsonl`
- backups under `data/lsr_v2_third_trade_close_execution_backups/` only when a close is actually executed.

## Expected disabled validation

With no close env variables enabled, the runner should return:

```text
status=WARN
decision=KEEP_DIAGNOSTIC_LSR_V2_THIRD_CLOSE_NOT_ENABLED
close_preflight_events=1
close_required_diagnostic_count=1
positions_closed_by_third_trade_close_execution=0
broker_close_called=false
paper_state_modified=false
paper_status_modified=false
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Expected armed execution

With explicit operator env and confirmation, the runner should close exactly one matching third LSR-v2 paper position and return:

```text
status=PASS
decision=LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED
positions_closed_by_third_trade_close_execution=1
orders_submitted_by_third_trade_close_execution=0
positions_opened_by_third_trade_close_execution=0
open_third_lsr_v2_positions_after=0
paper_status_open_positions_after=0
paper_state_modified=true
paper_status_modified=true
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Sandbox validation

Passed:

```text
python -m compileall -q trading_bot
PYTHONPATH=trading_bot python -m pytest -q trading_bot/tests/test_lsr_v2_third_trade_close_execution.py trading_bot/tests/test_lsr_v2_third_trade_close_preflight.py trading_bot/tests/test_lsr_v2_third_open_position_monitor.py trading_bot/tests/test_lsr_v2_third_trade_submit_execution.py trading_bot/test_paper_order_leakage_guard.py
```

Result:

```text
29 passed
```

Default-disabled runner on the current third trade state returned:

```text
status=WARN
decision=KEEP_DIAGNOSTIC_LSR_V2_THIRD_CLOSE_NOT_ENABLED
close_preflight_events=1
close_required_diagnostic_count=1
open_third_lsr_v2_positions_before=1
open_third_lsr_v2_positions_after=1
positions_closed_by_third_trade_close_execution=0
broker_close_called=false
paper_state_modified=false
paper_status_modified=false
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```
