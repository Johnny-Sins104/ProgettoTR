# Prompt 29.4.4s-10at — LSR-v2 third closed trade final audit / post-close reconciliation

## Scope

Adds an audit-only post-close reconciliation layer after `29.4.4s-10as`.

The patch verifies that the third supervised LSR-v2 paper trade has been closed and that the account is flat before any future re-entry or new trade work.

## Files

- `trading_bot/core/lsr_v2_third_closed_trade_final_audit.py`
- `trading_bot/run_lsr_v2_third_closed_trade_final_audit.py`
- `trading_bot/tests/test_lsr_v2_third_closed_trade_final_audit.py`
- `trading_bot/docs/PROMPT_29_4_4S10AT_THIRD_CLOSED_TRADE_FINAL_AUDIT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4S10AT_MANIFEST.txt`

## Behavior

The final audit reads:

- `data/lsr_v2_third_trade_close_execution_report.json`
- `data/lsr_v2_third_trade_close_execution.jsonl`
- `data/paper_state.json`
- `data/paper_status.json`
- close execution backup paths
- close operator environment variables

It writes only:

- `data/lsr_v2_third_closed_trade_final_audit_report.json`
- `data/lsr_v2_third_closed_trade_final_audit.jsonl`

## Pass criteria

`PASS / LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_READY` requires:

- close execution report present with `LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED`
- one close execution event found for the scoped cycle
- zero open positions after close
- zero open third LSR-v2 positions after close
- zero pending orders
- paper state/status consistency
- paper close backups present
- close operator env variables absent
- no submit, no new position, no re-entry
- live/testnet/exchange broker disabled
- operational unlock blocked

## Safety

This patch is audit-only. It never submits orders, never closes positions, never opens positions, never performs re-entry, and never mutates `paper_state.json` or `paper_status.json`.
