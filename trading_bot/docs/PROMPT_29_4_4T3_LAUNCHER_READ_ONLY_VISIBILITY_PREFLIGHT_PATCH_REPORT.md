# PROMPT 29.4.4t-3 — Launcher / avvia_bot_live read-only visibility preflight

## Scope

Audit-only preflight for the launcher layer after the LSR-v2 three-trade cycle has been closed, reconciled, locked, and surfaced in the paper runner footer.

This patch verifies that the Windows launcher path (`avvia_bot_live.bat` and `trading_bot/avvia_bot_live.py`) can safely receive a future read-only dashboard/lifecycle visibility banner without enabling live mode, re-entry, scheduler execution, broker calls, or Telegram network sends.

## Files

- `trading_bot/core/lsr_v2_launcher_read_only_visibility_preflight.py`
- `trading_bot/run_lsr_v2_launcher_read_only_visibility_preflight.py`
- `trading_bot/tests/test_lsr_v2_launcher_read_only_visibility_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T3_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T3_MANIFEST.txt`

## Safety contract

The patch is read-only and audit-only.

It does not:

- submit orders;
- open positions;
- close positions;
- call a broker;
- start a scheduler;
- send Telegram messages;
- make network calls;
- mutate `paper_state.json`;
- mutate `paper_status.json`;
- unlock a fourth trade;
- enable live mode;
- enable testnet;
- enable an exchange broker.

## Validation

Sandbox validation performed:

```powershell
python -m compileall -q trading_bot
PYTHONPATH=.:trading_bot pytest -q trading_bot/tests/test_lsr_v2_launcher_read_only_visibility_preflight.py
```

Result: `6 passed`.

Broader targeted sandbox validation with available LSR-v2/footer tests:

```powershell
PYTHONPATH=.:trading_bot pytest -q `
  trading_bot/tests/test_lsr_v2_launcher_read_only_visibility_preflight.py `
  trading_bot/test_paper_once_console_summary.py `
  trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py `
  trading_bot/tests/test_lsr_v2_engine_read_only_artifact_hook.py `
  trading_bot/tests/test_lsr_v2_paper_engine_integration_preflight.py `
  trading_bot/tests/test_lsr_v2_trade_lifecycle_auto_monitor.py `
  trading_bot/tests/test_lsr_v2_telegram_trade_dashboard.py `
  trading_bot/tests/test_lsr_v2_three_trade_postmortem_stability_lock.py `
  trading_bot/tests/test_lsr_v2_third_closed_trade_final_audit.py `
  trading_bot/tests/test_lsr_v2_third_trade_close_execution.py `
  trading_bot/tests/test_lsr_v2_third_trade_close_preflight.py
```

Result: `64 passed`.

The sandbox runner returns WARN when validated local artifacts are absent/stale. On the user's validated project state after `29.4.4t-2`, expected local decision is:

```text
LSR_V2_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT_READY
```

## Expected local PASS fields

```text
status=PASS
launcher_visibility_preflight_ready=true
launcher_visibility_allowed=false
launcher_mutation_allowed=false
launcher_execution_allowed=false
launcher_console_wiring_allowed=false
engine_hook_ready=true
integration_preflight_ready=true
lifecycle_auto_monitor_ready=true
telegram_dashboard_ready=true
three_trade_postmortem_ready=true
lifecycle_state=FLAT_LOCKED
telegram_payload_ready=true
telegram_update_ready=true
telegram_send_allowed=false
telegram_network_called=false
visual_sl_tp_progress_bar_ready=true
fourth_trade_allowed=false
fourth_trade_locked=true
stability_lock_active=true
orders_submitted_by_launcher_visibility_preflight=0
positions_opened_by_launcher_visibility_preflight=0
positions_closed_by_launcher_visibility_preflight=0
paper_state_modified_by_launcher_visibility_preflight=false
paper_status_modified_by_launcher_visibility_preflight=false
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Next patch

Recommended next patch:

```text
29.4.4t-4 — Launcher read-only dashboard banner/footer wiring
```

That future patch may print launcher-level read-only visibility, but it must still avoid live/testnet/exchange broker, order routing, re-entry, scheduler start, and Telegram network send.
