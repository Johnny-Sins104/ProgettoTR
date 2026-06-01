# Prompt 29.4.4u-22 — Generic LSR-v2 paper-only order-intent validation preflight

## Scope

This patch adds a generic LSR-v2 paper-only order-intent validation preflight.
It consumes the validated `29.4.4u-21` order-intent candidate audit and checks
whether the generic paper order-intent contract is ready for a future
materialization dry-run.

## Files

```text
trading_bot/core/lsr_v2_generic_paper_only_order_intent_validation_preflight.py
trading_bot/run_lsr_v2_generic_paper_only_order_intent_validation_preflight.py
trading_bot/tests/test_lsr_v2_generic_paper_only_order_intent_validation_preflight.py
trading_bot/docs/PROMPT_29_4_4U22_GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U22_MANIFEST.txt
```

## Contract checked

The preflight maps the future order-intent validation contract for:

```text
symbol
side
entry_price
stop_loss
take_profit
risk_amount
position_size
max_open_positions
paper_only
```

It confirms schema readiness and policy readiness for:

```text
max_open_positions = 1
paper_only = true
```

Runtime value validation is deliberately deferred because no real order intent
is materialized in this patch.

## Expected local result

```text
status = PASS
decision = LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_READY
generic_order_intent_validation_preflight_ready = true
paper_order_intent_contract_ready = true
paper_order_intent_contract_validatable = true
paper_order_intent_validated = false
paper_order_intent_materialized = false
paper_order_intent_persisted = false
paper_order_intent_ready = false
would_validate_order_intent = false
would_create_order_intent = false
would_submit = false
```

## Safety

This patch is preflight-only/read-only/fail-closed.

It does not:

```text
materialize paper_order_intent
persist paper_order_intent
submit orders
close orders
open positions
close positions
call a broker
start a scheduler
send Telegram network messages
mutate paper_state
mutate paper_status
enable live/testnet/exchange broker
create fifth/sixth/seventh trade ordinal modules
```

## Next patch

```text
29.4.4u-23 — Generic LSR-v2 paper-only order-intent materialization dry-run
```
