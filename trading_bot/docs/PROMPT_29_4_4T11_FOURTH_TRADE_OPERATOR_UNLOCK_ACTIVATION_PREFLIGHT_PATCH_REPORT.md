# Prompt 29.4.4t-11 — LSR-v2 guarded paper-only fourth-trade operator unlock activation preflight

## Scope

This patch adds a guarded activation preflight for the future LSR-v2 fourth-trade paper-only re-arm.

It is intentionally preflight-only, read-only, and fail-closed. It validates the t-10 operator unlock draft, upstream read-only artifacts, paper state/status, source markers, and optional operator activation controls. It does not activate candidate detection, routing, submit, close, scheduler, Telegram network send, or Paper Engine execution.

## Added files

- `trading_bot/core/lsr_v2_fourth_trade_operator_unlock_activation_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_operator_unlock_activation_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_operator_unlock_activation_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T11_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T11_MANIFEST.txt`

## Operator controls modeled

Future controls modeled by this preflight:

```text
LSR_V2_FOURTH_TRADE_REARM_ENABLE=1
LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION=I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY
LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS=1
```

If the controls are absent, the report can still pass in default fail-closed mode.

If the controls are present and correct, the report may mark:

```text
operator_unlock_activation_preflight_armed=true
operator_unlock_activation_would_unlock_fourth_trade=true
operator_unlock_activation_would_enable_candidate_detection=true
```

But actual execution permissions remain false.

## Safety contract

The patch always keeps:

```text
operator_unlock_activation_allowed=false
future_fourth_trade_unlock_allowed=false
fourth_trade_rearm_allowed=false
future_candidate_detection_allowed=false
candidate_routing_execution_allowed=false
candidate_submit_execution_allowed=false
paper_only_execution_allowed=false
future_integrated_operation_allowed=false
```

It also emits zero-action counters:

```text
orders_submitted_by_operator_unlock_activation_preflight=0
positions_opened_by_operator_unlock_activation_preflight=0
positions_closed_by_operator_unlock_activation_preflight=0
paper_state_modified_by_operator_unlock_activation_preflight=false
paper_status_modified_by_operator_unlock_activation_preflight=false
```

## Validation

Sandbox validation:

```text
python -m compileall -q trading_bot
PYTHONPATH=trading_bot python -m pytest -q trading_bot/tests/test_lsr_v2_fourth_trade_operator_unlock_activation_preflight.py
# 7 passed
```

Combined focused validation with t-10 draft tests:

```text
PYTHONPATH=trading_bot python -m pytest -q \
  trading_bot/tests/test_lsr_v2_fourth_trade_operator_unlock_activation_preflight.py \
  trading_bot/tests/test_lsr_v2_fourth_trade_operator_unlock_draft.py
# 14 passed
```

## Expected local default runner output

```text
status=PASS
decision=LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY
operator_unlock_activation_preflight_ready=true
operator_unlock_activation_preflight_armed=false
operator_unlock_activation_allowed=false
fourth_trade_rearm_allowed=false
future_candidate_detection_allowed=false
candidate_routing_execution_allowed=false
candidate_submit_execution_allowed=false
paper_only_execution_allowed=false
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Next patch

Recommended next patch after local validation:

```text
29.4.4t-12 — LSR-v2 guarded paper-only fourth-trade unlock activation / candidate detection preflight
```
