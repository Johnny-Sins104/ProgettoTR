# Prompt 29.4.4u-30 — Generic LSR-v2 supervised paper open-position monitor preflight

## Scope

This patch adds a preflight-only/read-only/fail-closed model for a future supervised paper open-position monitor. It consumes the `29.4.4u-29` submit execution report and checks whether a future monitor can be armed only after a real paper submit receipt and a real open paper position exist.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_open_position_monitor_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_open_position_monitor_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_open_position_monitor_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U30_GENERIC_LSR_V2_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U30_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_READY`

## Safety invariant

The patch does not monitor positions, does not close positions, does not submit orders, does not call any broker, does not mutate `paper_state` or `paper_status`, does not start a scheduler, does not send Telegram/network messages, and does not enable live/testnet/exchange execution.

Expected blocked runtime state:

- `broker_submit_receipt_available=false`
- `paper_open_position_available=false`
- `generic_open_position_monitor_allowed=false`
- `paper_open_position_monitor_ready=false`
- `generic_close_execution_allowed=false`
- `would_monitor_open_position=false`
- `would_call_paper_broker_close=false`
- `would_close=false`
- `would_submit=false`

## Next patch

`29.4.4u-31 — Generic LSR-v2 supervised paper close preflight`
