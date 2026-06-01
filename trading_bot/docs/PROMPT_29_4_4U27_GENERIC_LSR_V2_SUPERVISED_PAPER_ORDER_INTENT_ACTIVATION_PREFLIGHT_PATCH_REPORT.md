# Prompt 29.4.4u-27 — Generic LSR-v2 supervised paper-only order-intent activation preflight

## Scope

This patch adds a supervised paper-only order-intent activation preflight for the
generic LSR-v2 cycle. It consumes the validated `29.4.4u-26` submit execution
scaffold report and maps the future activation gate needed before a real
`paper_order_intent` can be created.

## Files

```text
trading_bot/core/lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py
trading_bot/run_lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py
trading_bot/tests/test_lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py
trading_bot/docs/PROMPT_29_4_4U27_GENERIC_LSR_V2_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U27_MANIFEST.txt
```

## Guarantees

The patch is preflight-only, read-only, and fail-closed.

It does not:

- create a real `paper_order_intent`
- validate runtime order-intent values
- materialize an order intent
- persist an order intent
- create a submit candidate
- submit an order
- close a position
- call a broker
- start a scheduler
- send Telegram network messages
- mutate `paper_state.json`
- mutate `paper_status.json`
- enable live, testnet, or exchange broker paths
- introduce ordinal trade expansion

## Expected PASS markers

```text
status = PASS
decision = LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT_READY
generic_supervised_paper_order_intent_activation_preflight_ready = true
generic_order_intent_activation_preflight_ready = true
paper_order_intent_activation_preflight_ready = true
order_intent_activation_preflight_diagnostic_available = true
order_intent_activation_contract_shape_modelable = true
generic_rearm_operator_gate_required = true
generic_rearm_operator_gate_satisfied = false
generic_order_intent_activation_allowed = false
paper_order_intent_activation_ready = false
paper_order_intent_materialized = false
paper_order_intent_persisted = false
would_activate_order_intent = false
would_create_order_intent = false
would_submit = false
```

## Next patch

```text
29.4.4u-28 — Generic LSR-v2 supervised paper-only order-intent activation
```
