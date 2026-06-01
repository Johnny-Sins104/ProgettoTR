# 29.4.4u-20 — Generic LSR-v2 paper-only handoff-to-order-intent dry-run preflight

## Scope

This patch consumes the validated `29.4.4u-19` route-to-handoff dry-run preflight and prepares a generic handoff-to-order-intent dry-run preflight.

It is intentionally dry-run/preflight-only, read-only, and fail-closed.

## Files

- `trading_bot/core/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py`

## Safety invariants

- No real `paper_order_intent` creation.
- No order-intent persistence.
- No submit.
- No close.
- No broker call.
- No scheduler.
- No Telegram network send.
- No `paper_state` mutation.
- No `paper_status` mutation.
- No live/testnet/exchange broker.
- No ordinal expansion.

## Expected decision

`LSR_V2_GENERIC_PAPER_ONLY_HANDOFF_TO_ORDER_INTENT_DRY_RUN_PREFLIGHT_READY`

## Expected next patch

`29.4.4u-21 — Generic LSR-v2 paper-only order-intent candidate audit`
