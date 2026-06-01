# Prompt 29.4.4u-63 — Generic LSR-v2 supervised paper runtime activation envelope execution scaffold

## Scope

This patch adds the Generic LSR-v2 supervised paper runtime activation envelope execution scaffold.
It consumes the validated `29.4.4u-62` runtime activation envelope preflight report and models a future runtime activation envelope execution step.

## Safety posture

The patch is scaffold-only, read-only by default, and fail-closed. It does not:

- build or activate a runtime envelope;
- run integrated operation;
- submit or close orders;
- call a broker;
- mutate `paper_state` or `paper_status`;
- start a scheduler;
- send Telegram or network messages;
- enable live, testnet, or exchange access;
- expand ordinal trade permissions.

## Required future evidence before activation

The scaffold keeps the explicit future runtime activation envelope execution patch requirement and requires complete runtime lifecycle evidence before any later execution can become possible:

- runtime activation envelope runtime evidence;
- terminal-ready synthesis runtime evidence;
- final-readiness-audit handoff runtime evidence;
- terminal lifecycle handoff runtime evidence;
- scheduler completion handoff runtime evidence;
- Telegram lifecycle-completion send runtime evidence;
- paper state/status terminal handoff mutation evidence;
- broker submit and close receipts;
- real close execution and closed paper position;
- realized PnL reconciliation/written evidence;
- lifecycle state complete;
- all operator gates;
- runtime order-intent values;
- paper-only mode with `max_open_positions=1`;
- live/testnet/exchange still disabled.

## Files added

- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_scaffold.py`
- `trading_bot/docs/PROMPT_29_4_4U63_GENERIC_LSR_V2_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_SCAFFOLD_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U63_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_SCAFFOLD_READY`

## Expected blocked flags

- `generic_runtime_activation_envelope_execution_scaffold_allowed=false`
- `generic_runtime_activation_envelope_allowed=false`
- `generic_runtime_activation_envelope_execution_allowed=false`
- `generic_integrated_operation_execution_allowed=false`
- `future_integrated_operation_allowed=false`
- `paper_runtime_activation_envelope_ready=false`
- `runtime_activation_envelope_runtime_executed=false`
- `would_build_runtime_activation_envelope=false`
- `would_run_runtime_activation_envelope=false`
- `would_run_integrated_operation=false`
- `would_submit=false`
- `would_close=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`

## Sandbox validation

- `python -m compileall -q trading_bot` — PASS
- `python -m pytest -q trading_bot/tests/test_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_scaffold.py` — 6 passed
- `python -m pytest -q trading_bot/tests/test_lsr_v2_generic*.py` — 186 passed
- `python trading_bot/run_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_scaffold.py` — PASS
