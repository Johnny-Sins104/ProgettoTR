# PROMPT 29.4.4t-14 — LSR-v2 Fourth-Trade Route Preflight

## Scope

Adds a read-only/fail-closed route preflight after the validated fourth-trade candidate detection audit.

## Files

- `trading_bot/core/lsr_v2_fourth_trade_route_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_route_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_route_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T14_FOURTH_TRADE_ROUTE_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T14_MANIFEST.txt`

## Behavior

The preflight reads validated upstream reports, `paper_state`, and `paper_status`. It checks whether the t-13 audit found a fourth-specific LSR-v2 candidate. If no fourth-specific candidate exists, the report still passes as a safe preflight but records:

- `route_candidate_available=false`
- `would_route=false`
- `would_submit=false`
- `route_blocked_reason=no_fourth_specific_candidate`

If a future fourth-specific candidate is present, the report may set `would_route=true` diagnostically, but execution permissions remain false.

## Safety contract

This patch never routes, submits, opens, closes, calls a broker, starts a scheduler, sends Telegram traffic, mutates `paper_state`, mutates `paper_status`, enables live/testnet/exchange, or unlocks the fourth trade.

Execution permissions remain false:

- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `paper_only_execution_allowed=false`
- `future_candidate_detection_allowed=false`
- `fourth_trade_rearm_allowed=false`

## Expected local outcome after validated t-13 data

- `status=PASS`
- `decision=LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY`
- `route_preflight_ready=true`
- `would_route=false` when `fourth_trade_candidate_detected_diagnostic=false`
- zero submit/open/close counters
- no state/status mutation
- live/testnet/exchange all false

## Next step

If the preflight is validated, the next planned patch is `29.4.4t-15 — LSR-v2 fourth-trade handoff dry-run`. If no fourth-specific candidate is available, that patch must remain non-routing and non-submit.
