# Prompt 29.4.4s-10am — LSR-v2 third paper trade submit preflight

## Scope

Adds a non-operational submit preflight layer for the third supervised LSR-v2 paper trade. It consumes the third-trade handoff dry-run artifacts from 29.4.4s-10al and produces a submit-preflight report/JSONL.

## Safety

- No order submission.
- No broker call.
- No position open/close.
- No paper_state mutation.
- No paper_status mutation.
- No live/testnet/exchange broker path.
- `third_trade_submit_enabled=false`.
- `third_trade_execute_enabled=false`.

## Expected ready decision

`LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_READY`

Expected counts when 10al is ready:

- `handoff_pass=true`
- `payload_valid_count=1`
- `would_prepare_submit_count=1`
- `would_submit_count=0`
- `would_submit_to_paper_broker_count=0`
- `orders_submitted_by_third_trade_submit_preflight=0`
- `positions_opened_by_third_trade_submit_preflight=0`
