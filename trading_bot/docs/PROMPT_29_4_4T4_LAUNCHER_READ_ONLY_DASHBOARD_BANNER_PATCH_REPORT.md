# PROMPT 29.4.4t-4 — Launcher read-only dashboard banner/footer wiring

## Scope

Adds read-only launcher visibility for the already validated LSR-v2 dashboard/lifecycle artifact snapshot.

The patch is visibility-only. It does not enable live trading, testnet trading, exchange brokers, order submission, position opening, position closing, scheduler execution, Telegram network send, or paper state/status mutation.

## Files

- `trading_bot/core/lsr_v2_launcher_read_only_dashboard_banner.py`
- `trading_bot/run_lsr_v2_launcher_read_only_dashboard_banner.py`
- `trading_bot/tests/test_lsr_v2_launcher_read_only_dashboard_banner.py`
- `trading_bot/avvia_bot_live.py`
- `avvia_bot_live.bat`
- `trading_bot/docs/PROMPT_29_4_4T4_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T4_MANIFEST.txt`

## Behavior

The new banner module reads:

- `data/lsr_v2_launcher_read_only_visibility_preflight_report.json`
- `data/lsr_v2_engine_read_only_artifact_hook_report.json`
- `data/lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `data/lsr_v2_telegram_trade_dashboard_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/paper_state.json`
- `data/paper_status.json`

It writes only:

- `data/lsr_v2_launcher_read_only_dashboard_banner_report.json`
- `data/lsr_v2_launcher_read_only_dashboard_banner.jsonl`

The launcher prints a read-only banner before starting the existing paper runner when artifacts are ready.

## Expected local PASS

- `status=PASS`
- `decision=LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY`
- `launcher_banner_ready=true`
- `launcher_banner_print_allowed=true`
- `lifecycle_state=FLAT_LOCKED`
- `telegram_send_allowed=false`
- `telegram_network_called=false`
- `scheduler_started=false`
- `fourth_trade_locked=true`
- `stability_lock_active=true`
- `orders_submitted_by_launcher_banner=0`
- `positions_opened_by_launcher_banner=0`
- `positions_closed_by_launcher_banner=0`
- `paper_state_modified_by_launcher_banner=false`
- `paper_status_modified_by_launcher_banner=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`

## Safety contract

- No live trading.
- No testnet trading.
- No exchange broker.
- No order submit.
- No position open.
- No position close.
- No scheduler start.
- No Telegram network send.
- No Telegram message send.
- No paper state/status mutation.
- No re-entry.
- No fourth trade unlock.

## Validation

Sandbox validation:

- `python -m compileall -q trading_bot` — PASS
- focused available targeted pytest suite — `70 passed`

Some broader local-only legacy tests are not available in the sandbox reconstruction, so the user should run the full targeted local validation command after installing the patch.
