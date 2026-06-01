# Prompt 29.4.4u-28 — Generic LSR-v2 supervised paper-only order-intent activation

## Scope

This patch adds a controlled activation-gate model for the generic LSR-v2 paper-only `paper_order_intent` path.

It consumes the validated u-27 artifact:

```text
lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json
```

and publishes:

```text
lsr_v2_generic_supervised_paper_order_intent_activation_report.json
lsr_v2_generic_supervised_paper_order_intent_activation.jsonl
```

## Added files

```text
trading_bot/core/lsr_v2_generic_supervised_paper_order_intent_activation.py
trading_bot/run_lsr_v2_generic_supervised_paper_order_intent_activation.py
trading_bot/tests/test_lsr_v2_generic_supervised_paper_order_intent_activation.py
trading_bot/docs/PROMPT_29_4_4U28_GENERIC_LSR_V2_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U28_MANIFEST.txt
```

## Expected decision

```text
LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_READY
```

## Activation model

The patch checks the future activation gate for a real generic paper order-intent:

```text
LSR_V2_GENERIC_REARM_ENABLE=1
LSR_V2_GENERIC_REARM_CONFIRMATION=I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY
LSR_V2_GENERIC_REARM_MAX_POSITIONS=1
```

It also requires real runtime values before real activation:

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

The default validated environment must keep the gate unsatisfied and the runtime values deferred.

## Read-only / fail-closed guarantees

This patch intentionally does not perform the following actions:

```text
no broker submit
no broker close
no submit candidate creation
no paper order-intent persistence
no paper_state mutation
no paper_status mutation
no scheduler start
no Telegram network send
no live broker
no testnet broker
no exchange broker
no ordinal trade expansion
```

Expected blocked fields in local validation:

```text
generic_rearm_operator_gate_satisfied = false
paper_order_intent_runtime_values_present = false
generic_order_intent_activation_allowed = false
paper_order_intent_activation_ready = false
paper_order_intent_materialized = false
paper_order_intent_persisted = false
would_activate_order_intent = false
would_create_order_intent = false
would_materialize_order_intent_real = false
would_persist_order_intent = false
would_submit = false
orders_submitted_by_generic_order_intent_activation = 0
positions_opened_by_generic_order_intent_activation = 0
paper_state_modified_by_generic_order_intent_activation = false
paper_status_modified_by_generic_order_intent_activation = false
```

## Local validation command

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main

$env:PYTHONPATH = "$PWD;$PWD\trading_bot"

python -m compileall -q trading_bot

python -m pytest -q `
  trading_bot\tests\test_lsr_v2_generic_supervised_paper_order_intent_activation.py `
  trading_bot\tests\test_lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py `
  trading_bot\tests\test_lsr_v2_generic_supervised_paper_submit_execution_scaffold.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_submit_candidate_audit.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_submit_readiness_preflight.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_validation_preflight.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_candidate_audit.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py

python trading_bot\run_lsr_v2_generic_supervised_paper_order_intent_activation.py
```

## Next patch

```text
29.4.4u-29 — Generic LSR-v2 supervised paper-only submit execution
```
