# 29.4.4u-18 — Generic LSR-v2 paper-only candidate route preflight

## Scope

This patch prepares a generic, non-ordinal candidate route preflight after the u-17 diagnostic candidate detection audit.

It reads diagnostic candidate evidence and builds a route-preflight map only. It does not execute routing and does not create a paper order intent.

## Safety

- Preflight-only
- Read-only
- Fail-closed
- No route execution
- No order intent creation
- No submit
- No close
- No broker calls
- No scheduler
- No Telegram/network send
- No paper_state mutation
- No paper_status mutation
- No live/testnet/exchange broker
- No ordinal fifth/sixth/seventh trade expansion

## Expected decision

`LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT_READY`

## Expected current-state interpretation

If u-17 found diagnostic candidates, u-18 may report diagnostic route-preflight availability and counts, but must keep:

- `route_candidate_available=false`
- `paper_order_intent_ready=false`
- `would_route=false`
- `would_create_order=false`
- `would_submit=false`
- `generic_route_execution_allowed=false`
- `generic_order_intent_creation_allowed=false`
