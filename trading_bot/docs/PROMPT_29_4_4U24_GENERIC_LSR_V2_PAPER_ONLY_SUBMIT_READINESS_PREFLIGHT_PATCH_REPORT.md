# PROMPT 29.4.4u-24 — Generic LSR-v2 paper-only submit readiness preflight

## Scope

This patch adds a generic LSR-v2 paper-only submit readiness preflight. It consumes the `29.4.4u-23` order-intent materialization dry-run artifact and verifies whether the dry-run order-intent payload has the shape and safety envelope needed for a future submit candidate audit.

## Files

```text
trading_bot/core/lsr_v2_generic_paper_only_submit_readiness_preflight.py
trading_bot/run_lsr_v2_generic_paper_only_submit_readiness_preflight.py
trading_bot/tests/test_lsr_v2_generic_paper_only_submit_readiness_preflight.py
trading_bot/docs/PROMPT_29_4_4U24_GENERIC_LSR_V2_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U24_MANIFEST.txt
```

## Guarantees

The patch is preflight-only, read-only, and fail-closed. It does not create a real `paper_order_intent`, does not persist an order intent, does not call a broker, does not submit orders, does not close positions, does not start schedulers, does not send Telegram messages, and does not mutate `paper_state` or `paper_status`.

## Expected local runner decision

```text
LSR_V2_GENERIC_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT_READY
```

## Expected PASS fields

```text
generic_submit_readiness_preflight_ready = true
paper_submit_readiness_preflight_ready = true
generic_submit_operator_gate_required = true
generic_submit_operator_gate_satisfied = false
paper_order_intent_dry_run_ready = true
paper_order_intent_runtime_values_present = false
paper_order_intent_ready = false
paper_submit_candidate_ready = false
paper_submit_execution_ready = false
generic_submit_execution_allowed = false
would_submit = false
would_call_paper_broker_submit = false
orders_submitted_by_generic_submit_readiness_preflight = 0
positions_opened_by_generic_submit_readiness_preflight = 0
paper_state_modified_by_generic_submit_readiness_preflight = false
paper_status_modified_by_generic_submit_readiness_preflight = false
live_enabled = false
testnet_enabled = false
exchange_broker_enabled = false
```

## Next patch

```text
29.4.4u-25 — Generic LSR-v2 paper-only submit candidate audit
```
