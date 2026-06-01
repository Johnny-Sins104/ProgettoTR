# Prompt 29.4.4t-16 — LSR-v2 fourth-trade submit preflight

## Scope

Submit-preflight-only/read-only/fail-closed audit for a future fourth LSR-v2 paper trade.

The patch consumes the validated `29.4.4t-15` fourth-trade handoff dry-run and upstream LSR-v2 reports. It determines whether a paper order intent would be valid for a future submit execution patch.

## Current expected behavior

Given the validated `29.4.4t-15` state with no fourth-specific route candidate:

- `route_candidate_available=false`
- `would_route=false`
- `would_create_order=false`
- `paper_order_intent_ready=false`

this patch must return PASS as a no-order diagnostic:

- `decision=LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY`
- `submit_preflight_ready=true`
- `would_submit=false`
- `broker_submit_called=false`
- `submit_blocked_reason=no_route_candidate_available`

## Safety invariants

The patch never:

- submits an order
- opens or closes positions
- calls a broker
- starts a scheduler
- sends Telegram/network traffic
- mutates `paper_state.json`
- mutates `paper_status.json`
- unlocks fourth-trade execution
- enables live/testnet/exchange broker

All execution permissions remain false.

## Files

- `trading_bot/core/lsr_v2_fourth_trade_submit_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_submit_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_submit_preflight.py`
