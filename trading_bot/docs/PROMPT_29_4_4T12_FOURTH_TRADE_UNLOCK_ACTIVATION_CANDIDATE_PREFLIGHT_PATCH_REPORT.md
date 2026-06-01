# PROMPT 29.4.4t-12 — LSR-v2 guarded paper-only fourth-trade unlock activation / candidate detection preflight

## Scope

This patch adds a guarded, fail-closed preflight for the future transition from the fourth-trade operator unlock activation model to candidate detection readiness.

It remains read-only and does not enable candidate detection, routing, submit, close, scheduler, Telegram network send, live, testnet, exchange broker, or Paper Engine execution.

## Files

- `trading_bot/core/lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T12_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T12_MANIFEST.txt`

## Expected default decision

`LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY`

Default behavior keeps all execution permissions disabled:

- `future_candidate_detection_allowed=false`
- `candidate_detection_allowed=false`
- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `paper_only_execution_allowed=false`
- `future_fourth_trade_unlock_allowed=false`
- `fourth_trade_rearm_allowed=false`

## Optional operator controls model

The preflight reads, but does not execute, these future controls:

- `LSR_V2_FOURTH_TRADE_REARM_ENABLE=1`
- `LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION=I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY`
- `LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS=1`

When valid, the report may set:

- `operator_unlock_activation_candidate_preflight_armed=true`
- `operator_unlock_activation_candidate_would_unlock_fourth_trade=true`
- `operator_unlock_activation_candidate_would_enable_candidate_detection=true`

Even then, all actual permissions remain false.

## Safety contract

- No orders submitted
- No positions opened
- No positions closed
- No broker call
- No scheduler start
- No Telegram network send
- No paper state mutation
- No paper status mutation
- No re-entry
- No fourth-trade unlock
- No live/testnet/exchange broker

## Local validation

```powershell
python -m compileall -q trading_bot
python -m pytest -q trading_bot\tests\test_lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py
python trading_bot\run_lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py
```

## Next patch

`29.4.4t-13 — LSR-v2 fourth-trade candidate detection audit`
