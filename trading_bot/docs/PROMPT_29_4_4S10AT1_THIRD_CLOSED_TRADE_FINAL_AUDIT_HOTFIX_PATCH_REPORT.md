# PROMPT 29.4.4s-10at-1 — LSR-v2 third closed trade final audit hotfix

## Scope

Hotfix for `29.4.4s-10at — LSR-v2 third closed trade final audit / post-close reconciliation`.

The previous final audit could incorrectly return `KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_CLOSE_NOT_CONFIRMED` after a valid third paper close if the operator later re-ran `run_lsr_v2_third_trade_close_execution.py` with close env disabled. That safe no-op run overwrote the close execution report with `KEEP_DIAGNOSTIC_LSR_V2_THIRD_POSITION_NOT_FOUND`, while the actual successful close remained in the close execution JSONL and paper event history.

## Fix

`core/lsr_v2_third_closed_trade_final_audit.py` now confirms the closed third trade from either:

1. the current close execution report when it is still the successful PASS report, or
2. the historical `LSR_V2_THIRD_TRADE_CLOSE_EXECUTION` event in the JSONL/paper event log when the current report has been overwritten by a later safe no-op run.

Backup verification now also scans `data/lsr_v2_third_trade_close_execution_backups/` when the latest close execution report no longer contains backup paths.

## Safety contract

This patch is audit-only.

It does not:

- close positions,
- open positions,
- submit orders,
- call a live/testnet/exchange broker,
- mutate `paper_state.json`,
- mutate `paper_status.json`,
- enable re-entry.

The final audit still requires:

- flat paper state,
- state/status consistency,
- close env variables absent,
- no submit/re-entry after close,
- live/testnet/exchange broker disabled,
- backup files present.

## Files

- `trading_bot/core/lsr_v2_third_closed_trade_final_audit.py`
- `trading_bot/tests/test_lsr_v2_third_closed_trade_final_audit.py`
- `trading_bot/docs/PROMPT_29_4_4S10AT1_THIRD_CLOSED_TRADE_FINAL_AUDIT_HOTFIX_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4S10AT1_MANIFEST.txt`

## Validation

Sandbox validation:

```powershell
python -m compileall -q trading_bot
PYTHONPATH=.:trading_bot python -m pytest -q trading_bot/tests/test_lsr_v2_third_closed_trade_final_audit.py
```

Result:

```text
6 passed
```

Regression added:

- pass when the latest close execution report is a safe `POSITION_NOT_FOUND` no-op but the historical successful close event and backup files are present.
