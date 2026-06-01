# PROMPT 29.4.4u-6 — Generic LSR-v2 paper cycle engine hook preflight

## Scope

This patch prepares a read-only, fail-closed preflight for a future Paper Engine hook that can expose the generic LSR-v2 paper-cycle model produced by the validated generic controller, order lifecycle, supervised re-arm policy, and integration preflight.

## Files

- `trading_bot/core/lsr_v2_generic_paper_cycle_engine_hook_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_engine_hook_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_engine_hook_preflight.py`

## Safety model

The patch is preflight-only and does not enable execution. It does not submit orders, open or close positions, call a broker, start a scheduler, send Telegram messages, mutate `paper_state.json`, mutate `paper_status.json`, or enable live/testnet/exchange broker operation.

All future execution flags remain false, including generic candidate detection, route, handoff, submit, close, final audit, postmortem, state mutation, and integrated operation.

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY`

## Next step

`29.4.4u-7 — Generic LSR-v2 paper cycle runner/launcher hook preflight`
