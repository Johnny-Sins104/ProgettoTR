# PROMPT 29.4.4u-43 — Generic LSR-v2 supervised paper lifecycle completion audit execution

## Scope

Adds a controlled, read-only-by-default, fail-closed lifecycle-completion audit execution gate.
The patch consumes the u-42 lifecycle-completion audit execution scaffold report and models the runtime evidence required before any lifecycle-completion audit can be considered executable.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_lifecycle_completion_audit_execution.py`

## Expected validation state

- `status=PASS`
- `decision=LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_READY`
- `generic_lifecycle_completion_audit_execution_model_ready=true`
- `generic_lifecycle_completion_audit_execution_patch_ready=true`
- `paper_lifecycle_completion_audit_execution_model_ready=true`
- `lifecycle_completion_audit_execution_diagnostic_available=true`
- `lifecycle_completion_audit_execution_diagnostic_count=401`

## Safety invariants

The patch keeps all runtime execution blocked in the current validation state:

- `generic_lifecycle_completion_audit_allowed=false`
- `generic_lifecycle_completion_audit_execution_allowed=false`
- `paper_lifecycle_completion_ready=false`
- `postmortem_runtime_executed=false`
- `final_audit_runtime_executed=false`
- `lifecycle_state=FLAT_LOCKED`
- `lifecycle_state_complete=false`
- `would_run_lifecycle_completion_audit=false`
- `would_submit=false`
- `would_close=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- no broker submit/close call
- no paper state/status mutation
- no live/testnet/exchange access

## Next patch

`29.4.4u-44 — Generic LSR-v2 supervised paper lifecycle state/status completion mutation preflight`
