# Prompt 29.4.4u-23 — Generic LSR-v2 paper-only order-intent materialization dry-run

## Scope

This patch adds a generic LSR-v2 paper-only order-intent materialization dry-run layer.
It consumes the validated `29.4.4u-22` order-intent validation preflight report and
builds a dry-run-only materialization map for the future generic paper order intent.

The patch deliberately does **not** create, persist, submit, close, or mutate anything.

## Added files

```text
trading_bot/core/lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py
trading_bot/run_lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py
trading_bot/tests/test_lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py
trading_bot/docs/PROMPT_29_4_4U23_GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U23_MANIFEST.txt
```

## Expected decision

```text
LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_READY
```

## Expected output markers

```text
generic_order_intent_materialization_dry_run_ready = true
paper_order_intent_dry_run_ready = true
paper_order_intent_materialization_dry_run_ready = true
paper_order_intent_materialization_simulated = true
would_materialize_order_intent_dry_run = true
paper_order_intent_runtime_values_present = false
paper_order_intent_runtime_values_required_before_real_materialization = true
paper_order_intent_validated = false
paper_order_intent_materialized = false
paper_order_intent_persisted = false
paper_order_intent_ready = false
would_validate_order_intent = false
would_create_order_intent = false
would_create_order = false
would_submit = false
```

## Safety guarantees

```text
DRY_RUN_ONLY
READ_ONLY
FAIL_CLOSED
NO_REAL_ORDER_INTENT_CREATION
NO_ORDER_INTENT_PERSISTENCE
NO_SUBMIT
NO_CLOSE
NO_BROKER_CALL
NO_STATE_MUTATION
NO_NETWORK_SEND
NO_SCHEDULER
NO_LIVE
NO_TESTNET
NO_EXCHANGE_BROKER
NO_ORDINAL_EXPANSION
```

## Validation commands

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main

$env:PYTHONPATH = "$PWD;$PWD\trading_bot"

python -m compileall -q trading_bot

python -m pytest -q `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_validation_preflight.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_candidate_audit.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py

python trading_bot\run_lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py
```

## Recommended next patch

```text
29.4.4u-24 — Generic LSR-v2 paper-only submit readiness preflight
```

`u-24` must remain preflight-only/read-only/fail-closed. It may inspect the dry-run
order-intent materialization map, but it must not submit orders, open positions, call a broker,
start a scheduler, send Telegram messages, or mutate paper state/status.
