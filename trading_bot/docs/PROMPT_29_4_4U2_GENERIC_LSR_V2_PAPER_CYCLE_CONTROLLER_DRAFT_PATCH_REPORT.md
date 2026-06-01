# PROMPT 29.4.4u-2 — Generic LSR-v2 paper cycle controller draft

## Scope

This patch introduces a generic LSR-v2 paper-cycle controller draft. It is read-only, draft-only, and fail-closed.

The purpose is to stop ordinal expansion (`fifth_trade_*`, `sixth_trade_*`, etc.) and define the reusable state-machine contract that will later manage paper-only LSR-v2 cycles with `trade_ordinal = N`.

## Added files

- `trading_bot/core/lsr_v2_paper_cycle_controller.py`
- `trading_bot/run_lsr_v2_paper_cycle_controller.py`
- `trading_bot/tests/test_lsr_v2_paper_cycle_controller.py`
- `trading_bot/docs/PROMPT_29_4_4U2_GENERIC_LSR_V2_PAPER_CYCLE_CONTROLLER_DRAFT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U2_MANIFEST.txt`

## Behavior

The controller draft reads the validated generic refactor preflight (`29.4.4u-1`) and the latest fourth-trade scaffold reports. It emits a generic state-machine plan covering:

1. `FLAT_LOCKED`
2. `READY_FOR_REARM_PREFLIGHT`
3. `CANDIDATE_DIAGNOSTIC`
4. `ROUTE_PREFLIGHT`
5. `HANDOFF_DRY_RUN`
6. `SUBMIT_PREFLIGHT`
7. `SUBMIT_EXECUTION_GUARDED`
8. `OPEN_MONITORING`
9. `CLOSE_PREFLIGHT`
10. `CLOSE_EXECUTION_GUARDED`
11. `FINAL_AUDIT`
12. `POSTMORTEM`
13. `COOLDOWN`

## Safety

The patch does not:

- submit orders
- open positions
- close positions
- call a broker
- mutate `paper_state.json`
- mutate `paper_status.json`
- start a scheduler
- send Telegram messages
- enable live/testnet/exchange brokers
- enable generic cycle execution
- generate ordinal trade modules

All execution permissions remain false.

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY`
