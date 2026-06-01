# PROMPT 29.4.4s-10u — LSR-v2 second trade rearm-aware route / order-intent preflight

## Scope

Adds a non-operational, second-trade-specific route and order-intent preflight. It reads the second-trade eligibility gate, the controlled re-arm gate, `paper_events.jsonl`, `paper_state.json`, and `paper_status.json`, then creates diagnostic second-trade route/order-intent events only when explicit route-only operator controls are present.

## Safety

- No new order.
- No new position.
- No close.
- No broker submit.
- No broker close.
- No paper state mutation.
- No paper status mutation.
- No live/testnet/exchange broker.
- `second_trade_execute_enabled=false`.
- `second_trade_submit_enabled=false`.
- `paper_order_submission_enabled=false`.

## Environment controls

```powershell
$env:LSR_V2_SECOND_TRADE_ROUTE_ENABLE="1"
$env:LSR_V2_SECOND_TRADE_ROUTE_CONFIRMATION="I_UNDERSTAND_SECOND_PAPER_TRADE_ROUTE_ONLY"
$env:LSR_V2_SECOND_TRADE_MAX_ORDERS="1"
```

## Outputs

- `data/lsr_v2_second_trade_route_preflight_report.json`
- `data/lsr_v2_second_trade_route_preflight.jsonl`

## Decisions

- `LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_CANDIDATE_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_OPERATOR_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN`
- `REJECT_LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_FAILED`
