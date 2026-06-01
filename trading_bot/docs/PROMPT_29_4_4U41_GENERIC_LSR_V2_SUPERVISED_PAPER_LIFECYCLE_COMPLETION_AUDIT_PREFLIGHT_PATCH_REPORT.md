# Prompt 29.4.4u-41 — Generic LSR-v2 supervised paper lifecycle completion audit preflight

## Scope

Adds a preflight-only, read-only, fail-closed lifecycle completion audit checkpoint for the generic LSR-v2 supervised paper path.

The patch consumes the `29.4.4u-40` postmortem execution report and models the future requirements for declaring one full supervised paper lifecycle complete and auditable.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U41_GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U41_MANIFEST.txt`

## Expected validation behavior

Expected state remains diagnostic-only:

- `generic_supervised_paper_lifecycle_completion_audit_preflight_ready=true`
- `generic_lifecycle_completion_audit_preflight_ready=true`
- `paper_lifecycle_completion_audit_preflight_ready=true`
- `lifecycle_completion_audit_preflight_diagnostic_available=true`
- `lifecycle_completion_audit_preflight_diagnostic_count=401`
- contract fields present and missing fields empty

Runtime completion remains blocked:

- `generic_lifecycle_completion_audit_allowed=false`
- `generic_lifecycle_completion_audit_execution_allowed=false`
- `paper_lifecycle_completion_ready=false`
- `would_run_lifecycle_completion_audit=false`
- `would_mutate_paper_state=false`
- `would_mutate_paper_status=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- `would_submit=false`
- `would_close=false`

## Required future runtime evidence

A real lifecycle completion audit remains unavailable until all of the following exist:

- real paper submit receipt
- real paper close receipt
- real close execution
- closed paper position
- realized PnL reconciled and written
- final audit runtime executed
- postmortem runtime executed
- lifecycle state complete
- all operator gates satisfied
- runtime values present and validated
- paper-only and max-open-positions policy satisfied

## Safety

This patch does not submit, close, reconcile PnL, run final audit, run postmortem, mutate state/status, send Telegram messages, start a scheduler, or touch live/testnet/exchange brokers.
