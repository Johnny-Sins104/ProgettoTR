# PROMPT 29.4.4s-10x — LSR-v2 second trade supervised submit boundary / armed single-order gate

## Scope

Adds a second-trade-specific submit boundary after `29.4.4s-10w`.

The patch consumes:

- `data/lsr_v2_second_trade_submit_preflight_report.json`
- `data/lsr_v2_second_trade_submit_preflight.jsonl`

and emits:

- `data/lsr_v2_second_trade_submit_boundary_report.json`
- `data/lsr_v2_second_trade_submit_boundary.jsonl`

## Intent

Allow the second LSR-v2 paper trade to reach an explicit `READY_ARMED` boundary while keeping execution disabled.

Required manual arming:

```powershell
$env:LSR_V2_SECOND_TRADE_SUBMIT_ARM="1"
$env:LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
$env:LSR_V2_SECOND_TRADE_MAX_ORDERS="1"
```

## Decisions

- `LSR_V2_SECOND_SINGLE_PAPER_SUBMIT_READY_ARMED`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_NOT_ARMED`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_PREFLIGHT_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_MAX_ORDER_CAP_BLOCKED`
- `REJECT_LSR_V2_SECOND_SUBMIT_BOUNDARY_FAILED`

## Safety invariants

The runner never calls a broker and never mutates state.

Hard-coded output invariants:

- `would_submit_count=0`
- `would_submit_to_paper_broker_count=0`
- `broker_submit_called=false`
- `orders_submitted_by_second_trade_submit_boundary=0`
- `positions_opened_by_second_trade_submit_boundary=0`
- `second_trade_submit_enabled=false`
- `second_trade_execute_enabled=false`
- `paper_order_submission_enabled=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`

## Validation

Sandbox validation passed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_submit_boundary.py
7 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_submit_boundary.py trading_bot/tests/test_lsr_v2_second_trade_submit_preflight.py trading_bot/tests/test_lsr_v2_second_trade_handoff_dry_run.py trading_bot/tests/test_lsr_v2_second_trade_route_preflight.py trading_bot/tests/test_lsr_v2_second_trade_rearm_gate.py trading_bot/tests/test_lsr_v2_second_trade_eligibility_gate.py
42 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_second_trade_submit_boundary.py trading_bot/run_lsr_v2_second_trade_submit_boundary.py
OK
```

## Operator note

This patch does not execute the second paper order. A separate execution patch is required if the operator decides to proceed.
