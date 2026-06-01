# Prompt 29.4.4u-52 — Generic LSR-v2 supervised paper integrated operation readiness execution

## Scope

This patch consumes the validated `29.4.4u-51` integrated-operation-readiness execution scaffold report and publishes the controlled execution model for the integrated operation readiness gate.

The patch intentionally remains read-only by default and fail-closed. It removes the explicit future integrated-operation execution patch blocker because this patch is that execution step, but it does not permit real integrated operation while runtime lifecycle evidence and operator gates are absent.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U52_GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U52_MANIFEST.txt`

## Safety invariants

- No submit.
- No close.
- No broker submit/close call.
- No scheduler start.
- No Telegram or network send.
- No paper_state mutation.
- No paper_status mutation.
- No live/testnet/exchange enablement.
- No ordinal expansion.

## Expected validation state

The runner should return `PASS` with decision:

`LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION_READY`

All real execution and mutation flags remain `false` because runtime lifecycle evidence is still absent.
