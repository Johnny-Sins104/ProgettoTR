# PROMPT 29.4.4u-13 — Generic LSR-v2 runtime snapshot footer/banner engine-runner read-only adapter hook

## Scope

This patch converts the validated `29.4.4u-12` engine-runner adapter preflight into a read-only adapter hook that publishes a reusable adapter payload between:

- generic runtime snapshot footer/banner read-only wiring hook
- Paper Engine
- paper runner
- Python launcher
- Windows launcher
- console visibility

## Files

- `trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py`
- `trading_bot/run_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py`
- `trading_bot/tests/test_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py`
- `trading_bot/docs/PROMPT_29_4_4U13_GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U13_MANIFEST.txt`

## Decision

Expected default decision after local validated upstream data:

`LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY`

## Safety contract

The patch is read-only and fail-closed.

It does not enable or perform:

- candidate detection execution
- route execution
- handoff execution
- broker submit
- broker close
- paper state mutation
- paper status mutation
- scheduler start
- Telegram network send
- live trading
- testnet trading
- exchange broker access
- ordinal trade-module expansion

All execution/mutation fields remain false and all submit/open/close counters remain zero.

## Validation

Sandbox validation:

- `py_compile` PASS
- focused pytest: `4 passed`
