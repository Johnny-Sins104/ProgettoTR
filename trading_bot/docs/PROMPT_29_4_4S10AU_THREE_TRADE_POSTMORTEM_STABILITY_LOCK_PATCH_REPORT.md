# PROMPT 29.4.4s-10au — LSR-v2 three-trade postmortem / stability lock

## Scope

Adds an audit-only three-trade postmortem and stability lock after the third supervised LSR-v2 paper trade has been closed and reconciled by `29.4.4s-10at-1`.

The patch consolidates the first, second, and third LSR-v2 supervised paper trade reports, verifies that the paper account is flat, confirms that no submit/re-entry path is active, and records a stability lock that keeps any fourth trade blocked until a future explicit observation/unlock patch is defined.

## Files

- `trading_bot/core/lsr_v2_three_trade_postmortem_stability_lock.py`
- `trading_bot/run_lsr_v2_three_trade_postmortem_stability_lock.py`
- `trading_bot/tests/test_lsr_v2_three_trade_postmortem_stability_lock.py`
- `trading_bot/docs/PROMPT_29_4_4S10AU_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4S10AU_MANIFEST.txt`

## Safety contract

This patch is audit-only:

- no paper order submit
- no paper close execution
- no position opening
- no position closing
- no re-entry
- no paper state mutation
- no paper status mutation
- no live mode
- no testnet mode
- no exchange broker
- no promotion readiness

It writes only:

- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock.jsonl`

## PASS requirements

The runner returns `PASS` with decision `LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY` only when all of the following are true:

- first closed-trade final audit passed
- first paper-trade postmortem passed
- second closed-trade final audit passed
- two-trade postmortem passed
- third submit execution passed
- third lifecycle report passed
- third close preflight passed
- third closed-trade final audit passed
- total submit execution count is exactly 3
- total close execution count is at least 3
- aggregate PnL/risk reconciliation is positive
- paper state is flat
- paper status is flat
- no pending orders are present
- no LSR-v2 operator env is still armed
- no fourth trade or re-entry is detected
- live/testnet/exchange broker remain disabled

## Decision map

- `LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_POSTMORTEM_INCOMPLETE`
- `KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_STATE_NOT_FLAT`
- `KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_PNL_RECONCILIATION_REQUIRED`
- `KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_OPERATOR_ENV_STILL_ACTIVE`
- `KEEP_DIAGNOSTIC_LSR_V2_FOURTH_TRADE_OR_REENTRY_DETECTED`
- `REJECT_LSR_V2_THREE_TRADE_POSTMORTEM_SAFETY_FAILED`

## Validation

Sandbox validation:

```powershell
python -m compileall -q trading_bot

$env:PYTHONPATH = "$PWD;$PWD\trading_bot"
python -m pytest -q `
  trading_bot\tests\test_lsr_v2_three_trade_postmortem_stability_lock.py `
  trading_bot\tests\test_lsr_v2_third_closed_trade_final_audit.py `
  trading_bot\tests\test_lsr_v2_third_trade_close_execution.py `
  trading_bot\tests\test_lsr_v2_third_trade_close_preflight.py `
  trading_bot\tests\test_lsr_v2_third_open_position_monitor.py `
  trading_bot\tests\test_lsr_v2_third_trade_submit_execution.py `
  trading_bot\test_paper_order_leakage_guard.py
```

Result: `42 passed` in sandbox.

## Operator notes

Do not start re-entry, re-arm, submit, or fourth-trade workflows after this patch. The expected next step after a validated PASS is an observation/cooldown design patch, not a new execution patch.
