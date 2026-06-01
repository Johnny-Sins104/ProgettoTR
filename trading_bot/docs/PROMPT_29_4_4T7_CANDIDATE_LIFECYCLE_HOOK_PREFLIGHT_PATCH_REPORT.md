# PROMPT 29.4.4t-7 — Paper Engine LSR-v2 candidate lifecycle hook preflight

## Scope

Adds a read-only preflight that verifies whether the Paper Engine can safely move toward a future LSR-v2 candidate lifecycle hook.

The patch does **not** re-arm the fourth trade, does **not** route candidates, does **not** submit or close paper positions, and does **not** modify `paper_state.json` or `paper_status.json`.

## Files

- `trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py`
- `trading_bot/run_lsr_v2_candidate_lifecycle_hook_preflight.py`
- `trading_bot/tests/test_lsr_v2_candidate_lifecycle_hook_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T7_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T7_MANIFEST.txt`

## Expected local decision

`LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY`

## Safety contract

The patch pins all execution permissions to false:

- `candidate_lifecycle_hook_allowed=false`
- `engine_candidate_lifecycle_hook_allowed=false`
- `future_candidate_detection_allowed=false`
- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `fourth_trade_rearm_allowed=false`
- `paper_only_execution_allowed=false`
- `future_integrated_operation_allowed=false`
- `paper_engine_mutation_allowed=false`
- `paper_engine_candidate_hook_mutation_allowed=false`

The patch never calls broker submit/close, never starts a scheduler, never sends Telegram messages, and never mutates state.

## Inputs

The preflight reads:

- `lsr_v2_launcher_runner_read_only_handoff_preflight_report.json`
- `lsr_v2_launcher_runner_visibility_parity_audit_report.json`
- `lsr_v2_engine_read_only_artifact_hook_report.json`
- `lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `lsr_v2_telegram_trade_dashboard_report.json`
- `lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `paper_state.json`
- `paper_status.json`
- selected source markers from Paper Engine, runner, lifecycle monitor and LSR-v2 candidate detector files

## Outputs

- `data/lsr_v2_candidate_lifecycle_hook_preflight_report.json`
- `data/lsr_v2_candidate_lifecycle_hook_preflight.jsonl`

## Validation

Expected local validation command:

```powershell
python -m compileall -q trading_bot
python -m pytest -q `
  trading_bot\tests\test_lsr_v2_candidate_lifecycle_hook_preflight.py `
  trading_bot\tests\test_lsr_v2_launcher_runner_read_only_handoff_preflight.py `
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
python trading_bot\run_lsr_v2_candidate_lifecycle_hook_preflight.py
```
