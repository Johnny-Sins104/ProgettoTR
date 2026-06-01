# PROMPT 29.4.4s-10y — LSR-v2 second supervised paper-only submit execution

## Scope

Adds the execution boundary for the **second** supervised LSR-v2 paper-only trade.
It consumes the `29.4.4s-10x` second-trade submit boundary artifacts and can submit at most one order through `PaperBrokerAdapter` only when a new execution arm and confirmation are provided.

## Files

- `trading_bot/core/lsr_v2_second_trade_submit_execution.py`
- `trading_bot/run_lsr_v2_second_trade_submit_execution.py`
- `trading_bot/tests/test_lsr_v2_second_trade_submit_execution.py`

## Inputs

- `data/lsr_v2_second_trade_submit_boundary_report.json`
- `data/lsr_v2_second_trade_submit_boundary.jsonl`
- `data/paper_state.json`
- `data/paper_status.json`

## Outputs

- `data/lsr_v2_second_trade_submit_execution_report.json`
- `data/lsr_v2_second_trade_submit_execution.jsonl`

## Manual controls

The second trade execution requires both the second submit boundary controls and the dedicated execution controls:

```powershell
$env:LSR_V2_SECOND_TRADE_SUBMIT_ARM="1"
$env:LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
$env:LSR_V2_SECOND_TRADE_EXECUTE="1"
$env:LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION="I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY"
$env:LSR_V2_SECOND_TRADE_MAX_ORDERS="1"
```

## Decisions

- `LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_NOT_ARMED`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_BOUNDARY_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_STATE_NOT_CLEAN`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_SUBMITTER_NOT_AVAILABLE`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_MAX_ORDER_CAP_BLOCKED`
- `REJECT_LSR_V2_SECOND_EXECUTION_SAFETY_FAILED`

## Safety invariants

- Paper mode only.
- Maximum one order.
- No batch orders.
- No retry loop.
- No re-entry.
- No close action.
- `live_enabled=false`.
- `testnet_enabled=false`.
- `exchange_broker_enabled=false`.
- `operational_unlock_allowed=false`.
- Execution requires clean paper state/status.

## Sandbox validation

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_submit_execution.py
8 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_submit_execution.py trading_bot/tests/test_lsr_v2_second_trade_submit_boundary.py trading_bot/tests/test_lsr_v2_second_trade_submit_preflight.py trading_bot/tests/test_lsr_v2_second_trade_handoff_dry_run.py
29 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_second_trade_submit_execution.py trading_bot/run_lsr_v2_second_trade_submit_execution.py
OK
```
