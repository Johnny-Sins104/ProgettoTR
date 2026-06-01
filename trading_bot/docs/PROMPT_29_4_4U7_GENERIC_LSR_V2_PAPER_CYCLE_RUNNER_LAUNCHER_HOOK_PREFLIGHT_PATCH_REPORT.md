# Prompt 29.4.4u-7 — Generic LSR-v2 paper cycle runner/launcher hook preflight

## Scope

This patch adds a read-only, fail-closed preflight for future runner/launcher visibility hooks for the generic LSR-v2 paper cycle.

It validates that the generic engine hook preflight, generic integration preflight, generic controller, generic order lifecycle, generic re-arm policy, existing launcher banner, and launcher/runner visibility parity are available and safe to expose in future runner/launcher surfaces.

## Files

- `trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U7_GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U7_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY`

## Safety guarantees

- No runner mutation.
- No launcher mutation.
- No Paper Engine mutation.
- No paper state/status mutation.
- No route execution.
- No submit.
- No close.
- No broker call.
- No scheduler start.
- No Telegram network send.
- No live, testnet, or exchange broker.
- No ordinal expansion (`fifth_trade_*`, `sixth_trade_*`, `seventh_trade_*`).

## Next step

`29.4.4u-8 — Generic LSR-v2 paper cycle read-only runtime snapshot hook`.
