# PROMPT 29.4.4u-44 — Generic LSR-v2 supervised paper lifecycle state/status completion mutation preflight

## Scope

Adds a preflight-only, read-only-by-default, fail-closed lifecycle state/status completion mutation checkpoint.
The patch consumes the u-43 lifecycle-completion audit execution report and models the runtime evidence required before any future paper lifecycle state/status completion mutation can be considered.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_preflight.py`

## Expected validation state

- `status=PASS`
- `decision=LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_PREFLIGHT_READY`
- `generic_lifecycle_state_status_completion_mutation_preflight_model_ready=true`
- `generic_lifecycle_state_status_completion_mutation_preflight_patch_ready=true`
- `paper_lifecycle_state_status_completion_mutation_preflight_ready=true`
- `lifecycle_state_status_completion_mutation_preflight_diagnostic_available=true`
- `lifecycle_state_status_completion_mutation_preflight_diagnostic_count=401`

## Safety invariants

The patch keeps all runtime execution and mutation blocked in the current validation state:

- `generic_lifecycle_state_status_completion_mutation_allowed=false`
- `generic_paper_state_completion_mutation_allowed=false`
- `generic_paper_status_completion_mutation_allowed=false`
- `generic_paper_state_mutation_allowed=false`
- `generic_paper_status_mutation_allowed=false`
- `paper_lifecycle_state_status_completion_mutation_ready=false`
- `paper_lifecycle_completion_ready=false`
- `postmortem_runtime_executed=false`
- `final_audit_runtime_executed=false`
- `lifecycle_completion_audit_runtime_executed=false`
- `lifecycle_state=FLAT_LOCKED`
- `lifecycle_state_complete=false`
- `would_mutate_paper_state=false`
- `would_mutate_paper_status=false`
- `would_submit=false`
- `would_close=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- no broker submit/close call
- no paper state/status mutation
- no live/testnet/exchange access

## Next patch

`29.4.4u-45 — Generic LSR-v2 supervised paper lifecycle state/status completion mutation execution scaffold`
