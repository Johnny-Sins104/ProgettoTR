# Prompt 29.4.4u-48 — Generic LSR-v2 supervised paper terminal lifecycle handoff execution scaffold

## Scope

This patch adds the terminal lifecycle handoff execution scaffold after the validated `29.4.4u-47` terminal lifecycle handoff preflight.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold.py`
- `trading_bot/docs/PROMPT_29_4_4U48_GENERIC_LSR_V2_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_SCAFFOLD_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U48_MANIFEST.txt`

## Behaviour

The patch consumes `data/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_preflight_report.json` from `29.4.4u-47` and models the future controlled terminal handoff execution scaffold.

The scaffold remains read-only by default and fail-closed. It does not perform terminal lifecycle handoff, mutate `paper_state` or `paper_status`, send Telegram/network messages, start a scheduler, call a broker, submit, close, or enable live/testnet/exchange access.

## Required future runtime evidence

The execution scaffold remains blocked until all complete lifecycle runtime evidence exists:

- broker submit receipt;
- broker close receipt;
- real close execution;
- closed paper position;
- realized PnL reconciliation and write;
- final audit runtime execution;
- postmortem runtime execution;
- lifecycle completion audit runtime execution;
- lifecycle state/status completion mutation runtime;
- terminal lifecycle handoff runtime;
- runtime values;
- all operator gates including terminal handoff confirmation.

## Expected validation result

Expected decision:

```text
LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_SCAFFOLD_READY
```

Expected safety flags remain false:

```text
generic_terminal_lifecycle_handoff_allowed=false
generic_terminal_lifecycle_handoff_execution_allowed=false
paper_terminal_lifecycle_handoff_ready=false
would_handoff_terminal_lifecycle=false
would_mutate_paper_state=false
would_mutate_paper_status=false
would_send_telegram=false
would_start_scheduler=false
would_submit=false
would_close=false
```

## Next patch

`29.4.4u-49 — Generic LSR-v2 supervised paper terminal lifecycle handoff execution`
