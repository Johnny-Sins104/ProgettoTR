# PROMPT 29.4.4u-11 — Generic LSR-v2 runtime snapshot footer/banner read-only wiring hook

## Scope

This patch introduces the first read-only runtime snapshot footer/banner wiring hook for the generic LSR-v2 paper cycle. It builds on the validated u-10 wiring preflight and publishes a reusable read-only payload for runner footer, launcher banner, console visibility, and safety fields.

## Files

- `trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py`
- `trading_bot/run_lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py`
- `trading_bot/tests/test_lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py`
- `trading_bot/docs/PROMPT_29_4_4U11_GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U11_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK_READY`

## Safety contract

The patch is read-only and fail-closed:

- no submit
- no close
- no broker call
- no scheduler start
- no Telegram network send
- no `paper_state` mutation
- no `paper_status` mutation
- no live/testnet/exchange broker
- no ordinal expansion

## Next patch

`29.4.4u-12 — Generic LSR-v2 runtime snapshot footer/banner engine-runner adapter preflight`
