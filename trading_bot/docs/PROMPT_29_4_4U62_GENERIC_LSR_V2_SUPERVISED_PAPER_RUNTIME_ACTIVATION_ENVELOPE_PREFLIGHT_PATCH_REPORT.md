# PROMPT 29.4.4u-62 — Generic LSR-v2 supervised paper runtime activation envelope preflight

## Scope

This patch adds a read-only, fail-closed preflight for a future generic supervised-paper runtime activation envelope.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_envelope_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_runtime_activation_envelope_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_runtime_activation_envelope_preflight.py`

## Upstream dependency

The patch consumes the `29.4.4u-61` terminal-ready synthesis execution report:

- `data/lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_report.json`

## Safety posture

The patch is preflight-only and does not:

- build or activate a runtime envelope;
- run integrated operation;
- submit or close orders;
- call broker adapters;
- mutate `paper_state` or `paper_status`;
- send Telegram/network messages;
- start a scheduler;
- enable live/testnet/exchange access;
- expand ordinal trade allowance.

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_PREFLIGHT_READY`

Runtime activation remains blocked until complete runtime lifecycle evidence, operator gates, runtime values, and a future explicit runtime activation envelope execution patch are present.
