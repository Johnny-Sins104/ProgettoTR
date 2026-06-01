# PROMPT 29.4.4u-5 — Generic LSR-v2 paper cycle integration preflight

## Scope

This patch adds a read-only, fail-closed integration preflight for the generic LSR-v2 paper-cycle architecture. It validates that the generic controller, paper order lifecycle, and supervised re-arm policy drafts can be treated as a coherent future integration plan without continuing ordinal `fifth_trade_*`, `sixth_trade_*`, or `seventh_trade_*` patch expansion.

## Added files

- `trading_bot/core/lsr_v2_generic_paper_cycle_integration_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_integration_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_integration_preflight.py`

## Read-only guarantees

The patch does not submit, open, close, route, mutate `paper_state`, mutate `paper_status`, start a scheduler, send Telegram messages, call any broker, or enable live/testnet/exchange operation.

All execution flags remain false:

- `generic_lsr_v2_paper_cycle_allowed=false`
- `generic_cycle_controller_execution_allowed=false`
- `generic_rearm_policy_execution_allowed=false`
- `generic_order_lifecycle_execution_allowed=false`
- `generic_candidate_detection_allowed=false`
- `generic_route_execution_allowed=false`
- `generic_handoff_execution_allowed=false`
- `generic_submit_execution_allowed=false`
- `generic_close_execution_allowed=false`
- `paper_only_execution_allowed=false`
- `future_integrated_operation_allowed=false`

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY`
