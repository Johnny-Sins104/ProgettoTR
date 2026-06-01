# Prompt 29.4.4u-61 — Generic LSR-v2 supervised paper integrated operation terminal-ready synthesis execution

## Scope

This patch adds the controlled terminal-ready synthesis execution gate for the generic LSR-v2 supervised paper integrated operation chain.

It consumes the `29.4.4u-60` terminal-ready synthesis execution scaffold report and removes the explicit future execution-patch blocker. It still requires complete runtime lifecycle evidence, terminal-ready synthesis runtime, final-readiness-audit handoff runtime, broker submit/close receipts, real close execution, closed paper position, realized PnL reconciliation/writing, all operator gates, runtime values, paper-only mode, `max_open_positions=1`, and live/testnet/exchange disabled before any future activation.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution.py`

## Safety

The patch is controlled, read-only by default, and fail-closed. It does not run integrated operation, synthesize terminal-ready runtime state, mutate paper state/status, send Telegram/network messages, start schedulers, submit, close, or call brokers.

Expected blocked flags remain false:

- `generic_integrated_operation_terminal_ready_synthesis_allowed`
- `generic_integrated_operation_terminal_ready_synthesis_execution_allowed`
- `generic_integrated_operation_execution_allowed`
- `future_integrated_operation_allowed`
- `would_run_integrated_operation_terminal_ready_synthesis`
- `would_run_integrated_operation`
- `would_submit`
- `would_close`
- `would_send_telegram`
- `would_start_scheduler`

## Expected validation

- `compileall`: PASS
- focused pytest: PASS
- generic LSR-v2 pytest set: PASS
- runner decision: `LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_READY`

## Next patch

`29.4.4u-62 — Generic LSR-v2 supervised paper runtime activation envelope preflight`
