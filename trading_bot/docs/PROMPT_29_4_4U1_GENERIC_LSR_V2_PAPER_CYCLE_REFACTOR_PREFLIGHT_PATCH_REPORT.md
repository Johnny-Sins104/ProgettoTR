# 29.4.4u-1 — Generic LSR-v2 paper cycle refactor preflight

Scope: read-only / preflight-only / fail-closed.

This patch stops the ordinal-trade expansion after the validated fourth-trade submit execution scaffold.  It prepares a generic LSR-v2 paper-cycle controller plan so future trades can be represented as `trade_ordinal=N` instead of adding `fifth_trade_*`, `sixth_trade_*`, etc.

## Adds

- `trading_bot/core/lsr_v2_generic_paper_cycle_refactor_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_refactor_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_refactor_preflight.py`

## Safety

The patch never submits, opens, closes, routes, starts schedulers, sends Telegram messages, calls brokers, or mutates `paper_state.json` / `paper_status.json`.

All execution permissions remain false:

- `generic_lsr_v2_paper_cycle_allowed=false`
- `generic_candidate_detection_allowed=false`
- `generic_route_execution_allowed=false`
- `generic_submit_execution_allowed=false`
- `generic_close_execution_allowed=false`
- `paper_only_execution_allowed=false`
- `future_integrated_operation_allowed=false`

Ordinal expansion is explicitly blocked:

- `ordinal_trade_patch_expansion_allowed=false`
- `fifth_trade_patch_allowed=false`
- `sixth_trade_patch_allowed=false`
- `seventh_trade_patch_allowed=false`

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY`
