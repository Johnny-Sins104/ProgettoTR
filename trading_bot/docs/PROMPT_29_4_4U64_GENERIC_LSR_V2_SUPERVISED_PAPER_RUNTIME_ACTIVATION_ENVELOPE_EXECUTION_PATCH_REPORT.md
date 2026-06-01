# PROMPT 29.4.4u-64 — Generic LSR-v2 supervised paper runtime activation envelope execution

## Scope

This patch adds a controlled runtime activation envelope execution gate. It consumes the `29.4.4u-63` runtime activation envelope execution scaffold report and removes only the explicit future execution-patch blocker. It remains read-only by default and fail-closed.

## Files added

- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U64_GENERIC_LSR_V2_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U64_MANIFEST.txt`

## Safety model

The patch does not submit orders, close positions, mutate paper state/status, call brokers, send Telegram/network messages, start schedulers, or enable live/testnet/exchange access. Runtime activation remains blocked until complete lifecycle runtime evidence, receipts, realized PnL, operator gates, runtime values, and explicit future activation controls are present.

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_READY`
