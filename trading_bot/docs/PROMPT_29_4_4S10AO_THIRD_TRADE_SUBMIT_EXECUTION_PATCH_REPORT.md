# PROMPT 29.4.4s-10ao — LSR-v2 third paper trade submit execution

## Scope

Adds the supervised execution boundary for the third LSR-v2 paper-only trade.
It consumes `29.4.4s-10an` submit-boundary artifacts and can submit exactly
one paper order only when all manual controls are present.

## Files

- `trading_bot/core/lsr_v2_third_trade_submit_execution.py`
- `trading_bot/run_lsr_v2_third_trade_submit_execution.py`
- `trading_bot/tests/test_lsr_v2_third_trade_submit_execution.py`

## Safety model

Default state is fail-closed. Without execution confirmation the runner emits:

- `KEEP_DIAGNOSTIC_LSR_V2_THIRD_EXECUTION_NOT_ARMED`
- `orders_submitted_by_third_trade_execution=0`
- `positions_opened_by_third_trade_execution=0`

Execution requires all of the following:

- `LSR_V2_THIRD_TRADE_SUBMIT_ARM=1`
- `LSR_V2_THIRD_TRADE_SUBMIT_CONFIRMATION=I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER`
- `LSR_V2_THIRD_TRADE_EXECUTE=1`
- `LSR_V2_THIRD_TRADE_EXECUTE_CONFIRMATION=I_UNDERSTAND_EXECUTE_THIRD_PAPER_ORDER_ONLY`
- `LSR_V2_THIRD_TRADE_MAX_ORDERS=1`
- `mode=paper`
- clean `paper_state.json` and `paper_status.json`
- submit boundary ready from `s-10an`

## Invariants

- no live trading
- no testnet
- no exchange broker
- no re-entry
- no batch orders
- max one paper order
- max one paper position opened
- no close action by this module
- `operational_unlock_allowed=false`
- `promotion_ready=false`

## Expected local validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_third_trade_submit_execution.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_third_trade_submit_execution.py --data-dir data
```

Expected without execute env:

```text
status=WARN
decision=KEEP_DIAGNOSTIC_LSR_V2_THIRD_EXECUTION_NOT_ARMED
orders_submitted_by_third_trade_execution=0
positions_opened_by_third_trade_execution=0
```

Manual execution:

```powershell
$env:LSR_V2_THIRD_TRADE_SUBMIT_ARM="1"
$env:LSR_V2_THIRD_TRADE_SUBMIT_CONFIRMATION="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"
$env:LSR_V2_THIRD_TRADE_EXECUTE="1"
$env:LSR_V2_THIRD_TRADE_EXECUTE_CONFIRMATION="I_UNDERSTAND_EXECUTE_THIRD_PAPER_ORDER_ONLY"
$env:LSR_V2_THIRD_TRADE_MAX_ORDERS="1"

python trading_bot\run_lsr_v2_third_trade_submit_execution.py --data-dir data

Remove-Item Env:\LSR_V2_THIRD_TRADE_SUBMIT_ARM
Remove-Item Env:\LSR_V2_THIRD_TRADE_SUBMIT_CONFIRMATION
Remove-Item Env:\LSR_V2_THIRD_TRADE_EXECUTE
Remove-Item Env:\LSR_V2_THIRD_TRADE_EXECUTE_CONFIRMATION
Remove-Item Env:\LSR_V2_THIRD_TRADE_MAX_ORDERS
```

Expected with manual execution:

```text
status=PASS
decision=LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED
orders_submitted_by_third_trade_execution=1
positions_opened_by_third_trade_execution=1
broker_submit_called=true
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```
