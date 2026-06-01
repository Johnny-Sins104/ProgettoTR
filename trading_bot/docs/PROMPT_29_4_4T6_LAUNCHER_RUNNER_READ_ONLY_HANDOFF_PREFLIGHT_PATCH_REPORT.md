# Prompt 29.4.4t-6 — Launcher/runner read-only handoff consolidation preflight

## Scope

Read-only preflight for a future consolidation handoff between launcher, runner footer, and Paper Engine LSR-v2 visibility artifacts.

This patch does not consolidate execution paths yet. It only verifies that the read-only handoff inputs are ready and safety-pinned before any later candidate lifecycle hook or paper-only re-arm work.

## Files

- `trading_bot/core/lsr_v2_launcher_runner_read_only_handoff_preflight.py`
- `trading_bot/run_lsr_v2_launcher_runner_read_only_handoff_preflight.py`
- `trading_bot/tests/test_lsr_v2_launcher_runner_read_only_handoff_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T6_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T6_MANIFEST.txt`

## Reads

- `data/lsr_v2_launcher_runner_visibility_parity_audit_report.json`
- `data/lsr_v2_launcher_read_only_dashboard_banner_report.json`
- `data/lsr_v2_engine_read_only_artifact_hook_report.json`
- `data/lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `data/lsr_v2_telegram_trade_dashboard_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- selected launcher/runner/engine source files for marker checks
- current `LSR_V2_*` operator envs

## Writes

- `data/lsr_v2_launcher_runner_read_only_handoff_preflight_report.json`
- `data/lsr_v2_launcher_runner_read_only_handoff_preflight.jsonl`

## PASS decision

`LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY`

PASS requires validated t-5 parity, t-4 launcher banner, t-1 engine hook, t-10ax lifecycle monitor, t-10aw dashboard, t-10au postmortem, flat state/status, no pending orders, no LSR-v2 operator envs, required source markers, no live/testnet/exchange broker, no scheduler, and no Telegram network/send.

## Safety

- No submit.
- No open.
- No close.
- No broker call.
- No scheduler.
- No Telegram network/send.
- No paper_state mutation.
- No paper_status mutation.
- No launcher/runner/engine mutation.
- No re-entry.
- No fourth-trade unlock.
- No live/testnet/exchange broker.

## Next recommended patch

`29.4.4t-7 — Paper Engine LSR-v2 candidate lifecycle hook preflight`
