# 29.4.4u-31 — Generic LSR-v2 supervised paper close preflight

## Scope

This patch adds a generic LSR-v2 supervised paper close preflight.

The patch consumes the validated `29.4.4u-30` open-position monitor preflight artifact and models the future close-preflight gate for a supervised paper position.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_close_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_close_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_close_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U31_GENERIC_LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U31_MANIFEST.txt`

## Safety

The patch is preflight-only, read-only, and fail-closed.

It does not:

- submit orders
- monitor an open position in runtime
- prepare a real close
- call a paper broker close
- close positions
- mutate `paper_state.json`
- mutate `paper_status.json`
- start schedulers
- send Telegram/network messages
- enable live, testnet, or exchange broker execution
- expand ordinal trade patches

## Expected validation state

The normal validation state remains blocked for execution because there is no broker submit receipt, no real open position, no active open-position monitor, no close trigger, no runtime values, and no operator close gate.

Expected runner decision:

```text
LSR_V2_GENERIC_SUPERVISED_PAPER_CLOSE_PREFLIGHT_READY
```

Expected execution/mutation flags:

```text
broker_submit_receipt_available = false
paper_open_position_available = false
paper_position_open = false
paper_open_position_monitor_ready = false
close_trigger_available = false
generic_close_execution_allowed = false
paper_close_execution_ready = false
would_prepare_close = false
would_call_paper_broker_close = false
would_close = false
would_submit = false
orders_submitted = 0
positions_opened = 0
positions_closed = 0
paper_state_modified = false
paper_status_modified = false
live/testnet/exchange = false
```

## Next patch

`29.4.4u-32 — Generic LSR-v2 supervised paper close execution scaffold`
