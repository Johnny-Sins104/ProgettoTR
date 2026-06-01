# PROMPT 29.4.4u-25 — Generic LSR-v2 paper-only submit candidate audit

## Scopo

Questa patch aggiunge un audit read-only/fail-closed per verificare se il modello di submit candidate paper-only generico è contrattualmente mappabile a partire dalla readiness `29.4.4u-24`.

## File aggiunti

```text
trading_bot/core/lsr_v2_generic_paper_only_submit_candidate_audit.py
trading_bot/run_lsr_v2_generic_paper_only_submit_candidate_audit.py
trading_bot/tests/test_lsr_v2_generic_paper_only_submit_candidate_audit.py
trading_bot/docs/PROMPT_29_4_4U25_GENERIC_LSR_V2_PAPER_ONLY_SUBMIT_CANDIDATE_AUDIT_PATCH_REPORT.md
docs/patch_reports/PATCH_29_4_4U25_MANIFEST.txt
```

## Vincoli di sicurezza

```text
audit-only
read-only
fail-closed
no submit candidate creation
no real paper_order_intent creation
no paper_order_intent persistence
no broker submit
no broker close
no order submitted
no position opened
no position closed
no paper_state mutation
no paper_status mutation
no scheduler
no Telegram network send
no live
no testnet
no exchange broker
no ordinal expansion
```

## Output atteso

```text
status = PASS
decision = LSR_V2_GENERIC_PAPER_ONLY_SUBMIT_CANDIDATE_AUDIT_READY
generic_submit_candidate_audit_ready = true
paper_submit_candidate_audit_ready = true
submit_candidate_audit_diagnostic_available = true
submit_candidate_contract_shape_modelable = true
paper_submit_candidate_ready = false
generic_submit_candidate_ready = false
paper_submit_execution_ready = false
generic_submit_execution_allowed = false
would_prepare_submit_candidate = false
would_call_paper_broker_submit = false
would_submit = false
```

## Prossima patch

```text
29.4.4u-26 — Generic LSR-v2 supervised paper submit execution scaffold
```
