# Prompt 29.4.4u-40 — Generic LSR-v2 supervised paper postmortem execution

## Scope

This patch adds the controlled postmortem-execution gate for the generic LSR-v2 supervised paper-only lifecycle.
It consumes the `29.4.4u-39` postmortem execution scaffold report and publishes a read-only/fail-closed model for future paper postmortem execution.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_postmortem_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_postmortem_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_postmortem_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U40_GENERIC_LSR_V2_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U40_MANIFEST.txt`

## Runtime behavior

The patch is intentionally non-mutating in the current validation state. It confirms that the postmortem execution model is shape-ready while preserving all execution blocks.

Expected ready markers:

- `generic_supervised_paper_postmortem_execution_ready=true`
- `generic_postmortem_execution_ready=true`
- `generic_postmortem_execution_model_ready=true`
- `generic_postmortem_execution_patch_ready=true`
- `paper_postmortem_execution_ready=true`
- `postmortem_execution_diagnostic_available=true`

Expected blocked markers:

- `generic_postmortem_execution_allowed=false`
- `generic_paper_state_mutation_allowed=false`
- `generic_paper_status_mutation_allowed=false`
- `would_run_postmortem=false`
- `would_mutate_paper_state=false`
- `would_mutate_paper_status=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- `would_submit=false`
- `would_close=false`

## Required future prerequisites before a real postmortem can be considered

- Real final-audit runtime execution.
- Broker submit and close receipts.
- Real close execution and a closed paper position.
- Realized PnL reconciliation and realized PnL write.
- Runtime order-intent values, not deferred sentinel values.
- Re-arm, submit, close, realized-PnL, final-audit, and postmortem operator gates.
- Paper-only mode and `max_open_positions=1`.
- Live/testnet/exchange broker disabled.

## Safety invariant

The patch does not submit, close, mutate paper state/status, send Telegram messages, start a scheduler, or access live/testnet/exchange brokers.
