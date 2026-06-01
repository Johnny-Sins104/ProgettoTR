# Prompt 29.4.4u-9 — Generic LSR-v2 paper cycle runtime snapshot visibility preflight

## Scope

This patch adds a read-only, fail-closed preflight that verifies how the generic LSR-v2 runtime snapshot can be surfaced consistently in runner/footer and launcher/banner visibility surfaces.

## Added files

- `trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U9_GENERIC_LSR_V2_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U9_MANIFEST.txt`

## Safety

The patch is visibility-preflight-only. It does not enable candidate detection, route execution, handoff execution, submit execution, close execution, broker calls, scheduler activity, Telegram network sends, or paper state/status mutation. It does not enable live, testnet, or exchange broker access and keeps ordinal trade expansion disabled.

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY`
