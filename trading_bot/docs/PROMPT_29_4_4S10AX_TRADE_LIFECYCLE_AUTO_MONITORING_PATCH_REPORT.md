# PROMPT 29.4.4s-10ax — LSR-v2 Trade Lifecycle Auto Monitoring

## Scope

Adds a monitoring-only lifecycle layer for the validated three-trade LSR-v2 paper cycle.

The patch reads the Telegram dashboard and stability-lock reports, classifies lifecycle state, and emits a Telegram-ready update payload. It does not start a scheduler, does not send Telegram messages, does not submit or close orders, and does not mutate `paper_state.json` or `paper_status.json`.

## Files

- `trading_bot/core/lsr_v2_trade_lifecycle_auto_monitor.py`
- `trading_bot/run_lsr_v2_trade_lifecycle_auto_monitor.py`
- `trading_bot/tests/test_lsr_v2_trade_lifecycle_auto_monitor.py`
- `trading_bot/docs/PROMPT_29_4_4S10AX_TRADE_LIFECYCLE_AUTO_MONITORING_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4S10AX_MANIFEST.txt`

## Safety Contract

- Paper-only monitoring.
- No scheduler starts in this patch.
- No Telegram network call.
- No order submission.
- No position opening.
- No position closing.
- No broker call.
- No `paper_state.json` mutation.
- No `paper_status.json` mutation.
- No re-entry.
- No fourth trade.
- No live/testnet/exchange broker.

## Expected Decision

`LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY`

Expected local state after validated 10aw:

- `lifecycle_state=FLAT_LOCKED`
- `lifecycle_update_ready=true`
- `telegram_update_ready=true`
- `scheduler_enabled=false`
- `telegram_network_called=false`
- `telegram_send_allowed=false`
- `fourth_trade_locked=true`
- `stability_lock_active=true`

## Next Patch

`29.4.4t — Paper Engine integration planning / runner consolidation preflight`
