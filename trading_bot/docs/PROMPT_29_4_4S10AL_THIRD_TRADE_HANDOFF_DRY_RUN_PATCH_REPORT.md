# Prompt 29.4.4s-10al — LSR-v2 third paper trade handoff dry-run

## Scope
Adds a dry-run handoff boundary after the third-trade route/order-intent preflight.
The module validates the third-trade order payload that would be handed to the
paper broker adapter, but it never calls the broker and never submits an order.

## Added files

- `trading_bot/core/lsr_v2_third_trade_handoff_dry_run.py`
- `trading_bot/run_lsr_v2_third_trade_handoff_dry_run.py`
- `trading_bot/tests/test_lsr_v2_third_trade_handoff_dry_run.py`

## Outputs

- `data/lsr_v2_third_trade_handoff_dry_run_report.json`
- `data/lsr_v2_third_trade_handoff_dry_run.jsonl`

## Safety invariants

- No live trading.
- No testnet trading.
- No exchange broker.
- No broker submit call.
- No paper order submission.
- No position opening.
- No position closing.
- No `paper_state.json` mutation.
- No `paper_status.json` mutation.

## Expected ready decision

`LSR_V2_THIRD_TRADE_HANDOFF_DRY_RUN_READY`

with:

- `payload_valid_count=1`
- `would_create_paper_order_count=1`
- `would_submit_count=0`
- `would_submit_to_paper_broker_count=0`
- `broker_submit_called=false`
- `orders_submitted_by_third_trade_handoff=0`
- `positions_opened_by_third_trade_handoff=0`
