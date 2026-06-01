# PROMPT 29.4.4s-10w — LSR-v2 second trade supervised submit preflight / disabled-by-default boundary

## Scope

Adds a second-trade-specific submit preflight layer after the second trade handoff dry-run. The layer reads the strict cycle-scoped handoff payload, verifies the second trade eligibility/re-arm/route/handoff chain, and emits `LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT` events.

## Files

- `trading_bot/core/lsr_v2_second_trade_submit_preflight.py`
- `trading_bot/run_lsr_v2_second_trade_submit_preflight.py`
- `trading_bot/tests/test_lsr_v2_second_trade_submit_preflight.py`

## Outputs

- `data/lsr_v2_second_trade_submit_preflight_report.json`
- `data/lsr_v2_second_trade_submit_preflight.jsonl`

## Safety

The patch is disabled-by-default and fail-closed:

- no broker submit
- no paper order submission
- no position opening
- no close
- no paper state mutation
- no paper status mutation
- no live
- no testnet
- no exchange broker
- `second_trade_execute_enabled=false`
- `second_trade_submit_enabled=false`
- `paper_order_submission_enabled=false`

## Expected ready decision

`LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT_READY`

with:

- `would_prepare_submit_count=1`
- `would_submit_count=0`
- `would_submit_to_paper_broker_count=0`
- `broker_submit_called=false`
- `orders_submitted_by_second_trade_submit_preflight=0`
- `positions_opened_by_second_trade_submit_preflight=0`
