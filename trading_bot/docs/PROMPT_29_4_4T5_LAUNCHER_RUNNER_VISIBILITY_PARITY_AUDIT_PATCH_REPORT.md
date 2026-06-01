# Prompt 29.4.4t-5 — Launcher/runner visibility parity audit

## Scope

Read-only parity audit between the LSR-v2 launcher dashboard banner and the
`run_paper_trading.py --once` runner footer visibility model.

This patch does not integrate execution logic. It only confirms that the same
validated LSR-v2 state is visible through both launcher and runner surfaces.

## Files

- `trading_bot/core/lsr_v2_launcher_runner_visibility_parity_audit.py`
- `trading_bot/run_lsr_v2_launcher_runner_visibility_parity_audit.py`
- `trading_bot/tests/test_lsr_v2_launcher_runner_visibility_parity_audit.py`
- `trading_bot/docs/PROMPT_29_4_4T5_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T5_MANIFEST.txt`

## Reads

- `data/lsr_v2_launcher_read_only_dashboard_banner_report.json`
- `data/lsr_v2_engine_read_only_artifact_hook_report.json`
- `data/lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `data/lsr_v2_telegram_trade_dashboard_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- current `LSR_V2_*` operator envs

## Writes

- `data/lsr_v2_launcher_runner_visibility_parity_audit_report.json`
- `data/lsr_v2_launcher_runner_visibility_parity_audit.jsonl`

## PASS decision

`LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY`

PASS requires:

- launcher dashboard banner report PASS;
- engine read-only artifact hook report PASS;
- lifecycle auto-monitor report PASS;
- Telegram dashboard report PASS;
- three-trade postmortem stability lock report PASS;
- launcher and runner footer visibility values match for lifecycle, Telegram
  readiness, visual SL/TP bar, fourth-trade lock, and stability lock;
- paper state/status flat and consistent;
- pending orders clear;
- no active LSR-v2 operator envs;
- no live/testnet/exchange broker flags;
- no re-entry/fourth trade unlock.

## Safety contract

This patch is audit-only/read-only:

- no order submission;
- no position opening;
- no position closing;
- no broker calls;
- no scheduler;
- no Telegram send/network call;
- no `paper_state` mutation;
- no `paper_status` mutation;
- no re-entry;
- no fourth-trade unlock;
- no live/testnet/exchange broker enablement.

## Expected local validation

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main
$env:PYTHONPATH = "$PWD;$PWD\trading_bot"
python -m compileall -q trading_bot
python -m pytest -q `
  trading_bot\tests\test_lsr_v2_launcher_runner_visibility_parity_audit.py `
  trading_bot\tests\test_lsr_v2_launcher_read_only_dashboard_banner.py `
  trading_bot\tests\test_lsr_v2_launcher_read_only_visibility_preflight.py `
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
python trading_bot\run_lsr_v2_launcher_runner_visibility_parity_audit.py
```

Expected runner fields:

- `status=PASS`
- `decision=LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY`
- `launcher_runner_visibility_parity_ok=true`
- `visibility_mismatch_detected=false`
- `lifecycle_state=FLAT_LOCKED`
- `telegram_send_allowed=false`
- `telegram_network_called=false`
- `visual_sl_tp_progress_bar_ready=true`
- `fourth_trade_locked=true`
- `stability_lock_active=true`
- zero submit/open/close counters
- no state/status mutation
- live/testnet/exchange false
