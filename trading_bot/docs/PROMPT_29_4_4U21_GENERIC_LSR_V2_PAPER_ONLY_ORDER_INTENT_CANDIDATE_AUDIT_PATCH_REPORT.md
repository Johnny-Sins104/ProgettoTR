# Prompt 29.4.4u-21 — Generic LSR-v2 paper-only order-intent candidate audit

## Scope

This patch adds an audit-only/read-only/fail-closed order-intent candidate audit after `29.4.4u-20`.
It consumes `data/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json` and audits whether the diagnostic order-intent context is modelable for a future validation/materialization stage.

## Files

```text
trading_bot/core/lsr_v2_generic_paper_only_order_intent_candidate_audit.py
trading_bot/run_lsr_v2_generic_paper_only_order_intent_candidate_audit.py
trading_bot/tests/test_lsr_v2_generic_paper_only_order_intent_candidate_audit.py
trading_bot/docs/PROMPT_29_4_4U21_GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U21_MANIFEST.txt
```

## Safety invariants

```text
audit-only = true
read-only = true
fail-closed = true
paper_order_intent_candidate_ready = false
paper_order_intent_ready = false
paper_order_intent_materialized = false
paper_order_intent_persisted = false
would_create_order_intent = false
would_submit = false
generic_order_intent_creation_allowed = false
generic_order_intent_persistence_allowed = false
generic_submit_execution_allowed = false
orders_submitted = 0
positions_opened = 0
positions_closed = 0
paper_state_modified = false
paper_status_modified = false
broker_submit_called = false
broker_close_called = false
telegram_network_called = false
scheduler_started = false
live_enabled = false
testnet_enabled = false
exchange_broker_enabled = false
```

## Expected runner decision

```text
status = PASS
decision = LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT_READY
generic_order_intent_candidate_audit_ready = true
order_intent_candidate_audit_diagnostic_available = true
paper_order_intent_candidate_ready = false
paper_order_intent_ready = false
would_create_order_intent = false
would_submit = false
```

If upstream `u-20` is missing/not ready, operator env variables are armed, or execution flags are not fail-closed, the runner returns `WARN` and keeps all execution/mutation fields false.

## Validation commands

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main

$env:PYTHONPATH = "$PWD;$PWD\trading_bot"

Get-ChildItem Env:LSR_V2*

python -m compileall -q trading_bot

python -m pytest -q `
  trading_bot\tests\test_lsr_v2_generic_paper_only_order_intent_candidate_audit.py `
  trading_bot\tests\test_lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py

python trading_bot\run_lsr_v2_generic_paper_only_order_intent_candidate_audit.py
```

## Next patch

```text
29.4.4u-22 — Generic LSR-v2 paper-only order-intent validation preflight
```
