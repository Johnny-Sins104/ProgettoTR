# Prompt 29.4.4t-15 — LSR-v2 fourth-trade handoff dry-run

## Scope

Adds a diagnostic-only, fail-closed dry-run layer after the validated fourth-trade route preflight.

## Files

- `trading_bot/core/lsr_v2_fourth_trade_handoff_dry_run.py`
- `trading_bot/run_lsr_v2_fourth_trade_handoff_dry_run.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_handoff_dry_run.py`

## Safety

The patch never submits, never opens/closes positions, never calls a broker, never starts a scheduler, never sends Telegram traffic, never touches live/testnet/exchange brokers, and never mutates `paper_state` or `paper_status`.

If no fourth-specific route candidate is available, the expected diagnostic output is `would_create_order=false` and `handoff_blocked_reason=no_route_candidate_available`.

## Expected decision

`LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY`
