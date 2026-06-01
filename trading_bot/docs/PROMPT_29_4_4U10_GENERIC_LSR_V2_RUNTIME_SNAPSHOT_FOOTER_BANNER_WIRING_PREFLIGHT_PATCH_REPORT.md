# 29.4.4u-10 — Generic LSR-v2 runtime snapshot footer/banner wiring preflight

## Scope

This patch prepares a read-only/fail-closed preflight for wiring the generic
LSR-v2 runtime snapshot into runner footer, launcher banner, and console
visibility surfaces.

## Files

- `trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight.py`
- `trading_bot/run_lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight.py`

## Safety

The patch does not submit orders, open positions, close positions, call a
broker, start a scheduler, send Telegram messages, or mutate `paper_state` or
`paper_status`. All runtime execution flags remain false.

## Expected decision

`LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT_READY`
