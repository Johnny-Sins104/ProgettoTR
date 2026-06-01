# Prompt 29.4.4u-46 — Generic LSR-v2 supervised paper lifecycle state/status completion mutation execution

## Scope

Adds a controlled, read-only-by-default, fail-closed lifecycle state/status completion mutation execution checkpoint. The patch consumes the u-45 lifecycle state/status completion mutation execution scaffold report and models the controlled gate for eventually mutating `paper_state` / `paper_status` into a completed lifecycle terminal state.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U46_GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U46_MANIFEST.txt`

## Safety contract

The patch must remain read-only and fail-closed in the current validation state. It must not submit, close, call a broker, mutate paper state/status, send Telegram messages, start a scheduler, or enable live/testnet/exchange access.

Expected blocked flags include:

```text
generic_lifecycle_state_status_completion_mutation_allowed = false
generic_lifecycle_state_status_completion_mutation_execution_allowed = false
generic_paper_state_completion_mutation_allowed = false
generic_paper_status_completion_mutation_allowed = false
generic_paper_state_mutation_allowed = false
generic_paper_status_mutation_allowed = false
paper_lifecycle_state_status_completion_mutation_ready = false
would_mutate_paper_state = false
would_mutate_paper_status = false
would_send_telegram = false
would_start_scheduler = false
would_submit = false
would_close = false
```

## Required runtime evidence before real state/status mutation

Real lifecycle state/status completion mutation remains blocked until all of the following exist at runtime:

- real broker submit receipt
- real broker close receipt
- real close execution
- closed paper position
- realized PnL reconciled and written
- final audit runtime execution
- postmortem runtime execution
- lifecycle completion audit runtime execution
- lifecycle state complete
- runtime values present and valid
- all explicit operator gates satisfied
- live/testnet/exchange disabled for paper-only operation

## Validation

Sandbox validation for package preparation passed with compileall, focused u-46 pytest, targeted regression through u-20, and the u-46 runner.

## Next patch

`29.4.4u-47 — Generic LSR-v2 supervised paper terminal lifecycle handoff preflight`.
