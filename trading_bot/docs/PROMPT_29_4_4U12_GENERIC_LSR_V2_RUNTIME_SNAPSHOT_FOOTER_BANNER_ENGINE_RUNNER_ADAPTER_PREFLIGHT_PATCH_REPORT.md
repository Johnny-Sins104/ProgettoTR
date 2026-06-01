# 29.4.4u-12 — Generic LSR-v2 runtime snapshot footer/banner engine-runner adapter preflight

## Scope

This patch adds a read-only/fail-closed preflight for the future adapter boundary between:

- generic runtime snapshot footer/banner read-only wiring hook
- Paper Engine
- paper runner
- launcher/banner surfaces
- console visibility payloads

It does not activate runtime execution or mutate any trading state.

## Added files

- `trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py`
- `trading_bot/run_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U12_GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U12_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT_READY`

## Safety invariants

The patch keeps the following disabled:

- generic runtime snapshot footer/banner engine-runner adapter execution
- engine read-only adapter execution
- paper runner adapter execution
- launcher adapter execution
- console visibility adapter execution
- candidate detection
- route execution
- handoff execution
- submit execution
- close execution
- Paper Engine mutation
- runner mutation
- launcher mutation
- paper_state mutation
- paper_status mutation
- Telegram network send
- scheduler start
- live/testnet/exchange broker
- ordinal trade patch expansion

## Runtime requirements

The preflight requires validated upstream reports from u-11, u-10, u-9, u-8, u-7, u-6, u-5, u-4, u-3, u-2, visibility parity/banner/engine hook, lifecycle dashboard and postmortem. It also checks source markers in the wiring hook, runtime snapshot hook, engine hook preflight, runner/launcher hook preflight, Paper Engine, paper runner, Python launcher, and Windows launcher.

## Local validation

Run:

```powershell
python -m compileall -q trading_bot
python -m pytest -q trading_bot\tests\test_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py
python trading_bot\run_lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py
```

Expected PASS fields include:

- `generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_ready=true`
- `generic_runtime_snapshot_footer_banner_engine_runner_adapter_plan_ready=true`
- `generic_runtime_snapshot_footer_banner_engine_runner_adapter_contract_ready=true`
- `generic_runtime_snapshot_footer_banner_engine_runner_adapter_map_ready=true`
- `engine_read_only_adapter_preflight_ready=true`
- `paper_runner_adapter_preflight_ready=true`
- `launcher_adapter_preflight_ready=true`
- `console_visibility_adapter_preflight_ready=true`
- all execution/mutation flags false
- no broker calls, no orders, no positions, no state mutation

## Next patch

`29.4.4u-13 — Generic LSR-v2 runtime snapshot footer/banner engine-runner read-only adapter hook`
