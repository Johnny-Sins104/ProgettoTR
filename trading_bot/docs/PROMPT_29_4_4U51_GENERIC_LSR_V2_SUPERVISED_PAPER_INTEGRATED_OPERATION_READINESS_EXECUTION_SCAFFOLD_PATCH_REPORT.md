# PROMPT 29.4.4u-51 — Generic LSR-v2 supervised paper integrated operation readiness execution scaffold

## Scope

This patch adds a scaffold-only execution-readiness layer for the future generic LSR-v2 supervised paper integrated operation. It consumes the validated `29.4.4u-50` integrated operation readiness preflight artifact and maps the next execution-scaffold gate without starting any integrated runtime.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution_scaffold.py`
- `trading_bot/docs/PROMPT_29_4_4U51_GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION_SCAFFOLD_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U51_MANIFEST.txt`

## Safety contract

The patch is intentionally scaffold-only, read-only by default, and fail-closed. It must keep all of the following false in the current validation state:

- `generic_integrated_operation_readiness_execution_scaffold_allowed`
- `generic_integrated_operation_allowed`
- `generic_integrated_operation_execution_allowed`
- `future_integrated_operation_allowed`
- `paper_integrated_operation_ready`
- `would_run_integrated_operation`
- `would_handoff_terminal_lifecycle`
- `would_mutate_paper_state`
- `would_mutate_paper_status`
- `would_send_telegram`
- `would_start_scheduler`
- `would_submit`
- `would_close`

It must not call a broker, submit, close, start a scheduler, send Telegram/network messages, mutate `paper_state`, mutate `paper_status`, enable live/testnet/exchange, or expand ordinal trade permissions.

## Runtime requirements kept blocked

The scaffold requires complete runtime lifecycle evidence before any future integrated-operation execution can be activated:

- terminal lifecycle handoff runtime
- scheduler completion handoff runtime
- Telegram lifecycle-completion send runtime
- paper state/status terminal handoff mutation runtime
- lifecycle state/status completion mutation runtime
- lifecycle completion audit runtime
- postmortem runtime
- final audit runtime
- broker submit and close receipts
- real close execution and a closed paper position
- realized-PnL reconciliation/write
- complete lifecycle state
- all prior operator gates plus the integrated-operation operator gate
- validated runtime values
- paper-only mode, `max_open_positions=1`, and live/testnet/exchange disabled
- explicit future integrated-operation execution patch

## Expected validation result

The expected local validation state is still blocked because no real paper lifecycle has run. The runner should return:

```text
status=PASS
decision=LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION_SCAFFOLD_READY
```

The PASS means the scaffold model is present and fail-closed, not that integrated operation is executable.

## Next patch

`29.4.4u-52 — Generic LSR-v2 supervised paper integrated operation readiness execution`
