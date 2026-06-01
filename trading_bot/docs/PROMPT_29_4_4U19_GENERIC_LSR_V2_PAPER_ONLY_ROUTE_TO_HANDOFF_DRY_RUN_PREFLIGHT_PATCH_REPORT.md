# PROMPT 29.4.4u-19 — Generic LSR-v2 paper-only route-to-handoff dry-run preflight

## Scope

This patch prepares a generic route-to-handoff dry-run preflight for the LSR-v2 paper-only cycle.
It consumes the generic candidate route preflight produced by `29.4.4u-18` and maps the diagnostic route evidence into a future handoff dry-run context.

## Added files

- `trading_bot/core/lsr_v2_generic_paper_only_route_to_handoff_dry_run_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_only_route_to_handoff_dry_run_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_only_route_to_handoff_dry_run_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U19_GENERIC_LSR_V2_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U19_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_READY`

## Safety contract

The patch is dry-run/preflight-only, read-only, and fail-closed.
It does not perform route execution, handoff execution, paper order intent creation, broker submit/close, position open/close, scheduler start, Telegram/network send, paper state mutation, paper status mutation, live trading, testnet trading, exchange broker trading, or ordinal module expansion.

## Expected current-state behavior

When `u-18` reports diagnostic route evidence, the preflight may expose diagnostic availability and count, but it must keep operational fields disabled:

- `route_candidate_available=false`
- `route_preflight_candidate_available=false`
- `handoff_candidate_available=false`
- `paper_order_intent_ready=false`
- `would_route=false`
- `would_handoff=false`
- `would_create_order=false`
- `would_submit=false`
- `generic_handoff_execution_allowed=false`
- `generic_order_intent_creation_allowed=false`
- `orders_submitted_by_generic_route_to_handoff_dry_run_preflight=0`
- `positions_opened_by_generic_route_to_handoff_dry_run_preflight=0`
- `positions_closed_by_generic_route_to_handoff_dry_run_preflight=0`

## Recommended next patch

`29.4.4u-20 — Generic LSR-v2 paper-only handoff-to-order-intent dry-run preflight`
