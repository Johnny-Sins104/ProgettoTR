# Prompt 29.4.4u-67 — Generic LSR-v2 supervised paper integrated dry-run runtime bundle

## Scope

This macro-patch bundles three homogeneous readiness-gate steps into one patch:

1. Generic supervised paper integrated dry-run runtime preflight
2. Generic supervised paper integrated dry-run runtime execution scaffold
3. Generic supervised paper integrated dry-run runtime execution

The bundle consumes the validated `29.4.4u-66` paper runtime arming bundle report:

`data/lsr_v2_generic_supervised_paper_runtime_arming_bundle_report.json`

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_bundle.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_preflight.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_execution_scaffold.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_bundle.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_bundle.py`
- `trading_bot/docs/PROMPT_29_4_4U67_GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_DRY_RUN_RUNTIME_BUNDLE_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U67_MANIFEST.txt`

## Safety model

The patch is read-only by default and fail-closed. It does not:

- run a real integrated dry-run runtime
- arm paper runtime
- build or run runtime activation envelope
- run integrated operation
- submit orders
- close positions
- call a broker
- mutate `paper_state`
- mutate `paper_status`
- start a scheduler
- send Telegram or network messages
- enable live/testnet/exchange access
- expand ordinal trade permissions

## Gate behavior

The execution substep removes only the explicit future integrated-dry-run-runtime execution patch blocker because this macro-patch contains the execution step. It still requires complete runtime lifecycle evidence before any future runtime can become real:

- integrated dry-run runtime real
- paper runtime arming runtime real
- runtime activation terminal audit runtime real
- runtime activation envelope runtime real
- terminal-ready synthesis runtime real
- final-readiness-audit handoff/runtime evidence
- terminal lifecycle handoff runtime
- scheduler completion handoff runtime
- Telegram lifecycle-completion send runtime
- paper state/status terminal handoff mutation
- broker submit/close receipts
- real close execution
- closed paper position
- realized PnL written
- lifecycle complete
- runtime values present
- required operator gates satisfied
- paper-only mode
- `max_open_positions=1`
- live/testnet/exchange disabled

## Expected validation state

In the current validation state all real runtime evidence remains absent, so the bundle returns `PASS` while keeping every execution path blocked.

Expected final decision:

`LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_DRY_RUN_RUNTIME_BUNDLE_READY`

Expected next patch:

`29.4.4u-68 — Generic LSR-v2 supervised paper order-intent real runtime activation bundle`
