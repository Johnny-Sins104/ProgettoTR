# Prompt 29.4.4u-60 — Generic LSR-v2 supervised paper integrated operation terminal-ready synthesis execution scaffold

## Scope

This patch adds the terminal-ready synthesis execution scaffold for the generic LSR-v2 supervised paper integrated operation chain.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold.py`

## Safety

The patch is scaffold-only, read-only by default, and fail-closed. It does not run integrated operation, synthesize terminal-ready runtime state, mutate paper state/status, send Telegram/network messages, start schedulers, submit, close, or call brokers.

## Expected validation

- `compileall`: PASS
- focused pytest: PASS
- runner decision: `LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_READY`

## Next patch

`29.4.4u-61 — Generic LSR-v2 supervised paper integrated operation terminal-ready synthesis execution`
