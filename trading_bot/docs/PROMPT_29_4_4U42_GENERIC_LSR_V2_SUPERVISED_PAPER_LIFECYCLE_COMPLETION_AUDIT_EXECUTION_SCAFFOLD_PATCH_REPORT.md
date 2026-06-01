# PROMPT 29.4.4u-42 — Generic LSR-v2 supervised paper lifecycle completion audit execution scaffold

## Scope

Adds a scaffold-only, read-only, fail-closed lifecycle-completion audit execution checkpoint.
The patch consumes the u-41 lifecycle-completion audit preflight report and models the future execution contract for lifecycle-completion auditing without performing any runtime audit, mutation, broker call, Telegram send, scheduler start, live/testnet operation, or ordinal expansion.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution_scaffold.py`

## Expected validation state

- `status=PASS`
- `decision=LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_SCAFFOLD_READY`
- `generic_lifecycle_completion_audit_execution_scaffold_ready=true`
- `paper_lifecycle_completion_audit_execution_scaffold_ready=true`
- `lifecycle_completion_audit_execution_scaffold_diagnostic_available=true`
- `lifecycle_completion_audit_execution_scaffold_diagnostic_count=401`

## Safety invariants

The patch keeps all runtime execution blocked:

- `generic_lifecycle_completion_audit_allowed=false`
- `generic_lifecycle_completion_audit_execution_allowed=false`
- `paper_lifecycle_completion_ready=false`
- `postmortem_runtime_executed=false`
- `final_audit_runtime_executed=false`
- `would_run_lifecycle_completion_audit=false`
- `would_submit=false`
- `would_close=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- no broker submit/close call
- no paper state/status mutation
- no live/testnet/exchange access

## Next patch

`29.4.4u-43 — Generic LSR-v2 supervised paper lifecycle completion audit execution`
