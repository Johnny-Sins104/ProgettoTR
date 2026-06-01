# Prompt 29.4.4u-59 — Generic LSR-v2 supervised paper integrated operation terminal-ready synthesis preflight

## Scope

Adds a read-only/fail-closed terminal-ready synthesis preflight for the generic LSR-v2 supervised paper integrated-operation path. The patch consumes the validated u-58 final-readiness-audit handoff execution artifact and models the prerequisites for a future terminal-ready synthesis execution patch.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U59_GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U59_MANIFEST.txt`

## Safety contract

The patch does not submit, close, call a broker, mutate `paper_state` or `paper_status`, start a scheduler, send Telegram/network messages, or enable live/testnet/exchange access. It preserves fail-closed flags until complete runtime lifecycle evidence, terminal-ready synthesis runtime, final-readiness-audit handoff runtime, broker receipts, runtime values, and all operator gates are present.

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_PREFLIGHT_READY`
