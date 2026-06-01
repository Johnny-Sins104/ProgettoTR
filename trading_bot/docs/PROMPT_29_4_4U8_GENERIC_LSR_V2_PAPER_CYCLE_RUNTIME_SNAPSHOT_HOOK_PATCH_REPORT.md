# Prompt 29.4.4u-8 — Generic LSR-v2 paper cycle read-only runtime snapshot hook

## Scope

This patch adds a read-only, fail-closed runtime snapshot hook for the generic LSR-v2 paper cycle.

It consolidates the generic runner/launcher hook preflight, generic engine hook preflight, generic integration preflight, generic controller, generic order lifecycle, generic re-arm policy, existing engine artifact hook, and existing runner/launcher visibility into a single runtime snapshot artifact.

## Files

- `trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py`
- `trading_bot/docs/PROMPT_29_4_4U8_GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U8_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY`

## Safety guarantees

- Runtime snapshot only.
- No engine mutation.
- No runner mutation.
- No launcher mutation.
- No paper state/status mutation.
- No candidate execution.
- No route execution.
- No submit.
- No close.
- No broker call.
- No scheduler start.
- No Telegram network send.
- No live, testnet, or exchange broker.
- No ordinal expansion (`fifth_trade_*`, `sixth_trade_*`, `seventh_trade_*`).

## Next step

`29.4.4u-9 — Generic LSR-v2 paper cycle runtime snapshot visibility preflight` or wait for a real candidate.
