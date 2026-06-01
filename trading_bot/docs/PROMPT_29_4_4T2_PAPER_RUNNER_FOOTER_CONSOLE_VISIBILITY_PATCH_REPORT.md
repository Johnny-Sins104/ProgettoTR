# Prompt 29.4.4t-2 — Paper runner footer / console visibility consolidation

## Scope

This patch surfaces the validated LSR-v2 dashboard/lifecycle artifact state in the paper `--once` footer and runner fallback footer.

The patch remains console/read-only. It does not consolidate runners yet, does not start a scheduler, does not send Telegram messages, and does not submit/open/close paper positions.

## Files changed

- `trading_bot/core/paper_once_console_summary.py`
- `trading_bot/core/paper_once_runner_footer.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/test_paper_once_console_summary.py`
- `trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py`

## Behavior

The once footer now includes LSR-v2 engine artifact visibility when the read-only artifact hook report is available:

- `lsr_v2_engine_hook_decision`
- `lsr_v2_lifecycle_state`
- `lsr_v2_engine_artifact_hook_ready`
- `lsr_v2_paper_engine_hook_read_only`
- `lsr_v2_dashboard_ready`
- `lsr_v2_telegram_payload_ready`
- `lsr_v2_telegram_update_ready`
- `lsr_v2_telegram_send_allowed`
- `lsr_v2_visual_sl_tp_progress_bar_ready`
- `lsr_v2_visual_sl_tp_progress_bar`
- `lsr_v2_fourth_trade_locked`
- `lsr_v2_stability_lock_active`
- zero submit/open/close counters for the artifact hook

The runner fallback footer loads `data/lsr_v2_engine_read_only_artifact_hook_report.json` and emits a fail-closed missing-report block when unavailable.

## Safety contract

- No order submission.
- No position opening.
- No position closing.
- No broker call.
- No scheduler start.
- No Telegram network call.
- No Telegram send.
- No `paper_state.json` mutation.
- No `paper_status.json` mutation.
- No re-entry.
- No fourth trade unlock.
- No live/testnet/exchange broker.

The fallback footer force-pins hostile or malformed report fields to safe values:

- `telegram_send_allowed=false`
- `telegram_network_called=false`
- `scheduler_enabled=false`
- `scheduler_started=false`
- `orders_submitted_by_engine_artifact_hook=0`
- `positions_opened_by_engine_artifact_hook=0`
- `positions_closed_by_engine_artifact_hook=0`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`

## Expected local validation

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main
$env:PYTHONPATH = "$PWD;$PWD\trading_bot"

Get-ChildItem Env:LSR_V2*
python -m compileall -q trading_bot
python -m pytest -q `
  trading_bot\test_paper_once_console_summary.py `
  trading_bot\tests\test_paper_once_runner_footer_lsr_v2.py `
  trading_bot\tests\test_lsr_v2_engine_read_only_artifact_hook.py `
  trading_bot\tests\test_lsr_v2_paper_engine_integration_preflight.py `
  trading_bot\tests\test_lsr_v2_trade_lifecycle_auto_monitor.py `
  trading_bot\tests\test_lsr_v2_telegram_trade_dashboard.py `
  trading_bot\tests\test_lsr_v2_three_trade_postmortem_stability_lock.py `
  trading_bot\tests\test_lsr_v2_third_closed_trade_final_audit.py `
  trading_bot\tests\test_lsr_v2_third_trade_close_execution.py `
  trading_bot\tests\test_lsr_v2_third_trade_close_preflight.py `
  trading_bot\tests\test_lsr_v2_third_open_position_monitor.py `
  trading_bot\tests\test_lsr_v2_third_trade_submit_execution.py `
  trading_bot\test_paper_order_leakage_guard.py
```

Expected runner/console state after a paper once cycle or fallback footer:

- `prompt=29.4.4t-2`
- `lsr_v2_engine_hook_decision=LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY`
- `lsr_v2_lifecycle_state=FLAT_LOCKED`
- `lsr_v2_dashboard_ready=true`
- `lsr_v2_telegram_payload_ready=true`
- `lsr_v2_telegram_update_ready=true`
- `lsr_v2_telegram_send_allowed=false`
- `lsr_v2_visual_sl_tp_progress_bar_ready=true`
- `lsr_v2_fourth_trade_locked=true`
- `lsr_v2_stability_lock_active=true`
- zero artifact-hook submit/open/close counters

## Sandbox validation

- `python -m compileall -q trading_bot` — PASS
- Targeted pytest suite — PASS, 75 tests

## Recommended next patch

`29.4.4t-3 — Paper Engine read-only lifecycle/dashboard footer smoke in once runner` or the next integration step only after operator review. Keep it read-only until a separate explicit consolidation patch is approved.
