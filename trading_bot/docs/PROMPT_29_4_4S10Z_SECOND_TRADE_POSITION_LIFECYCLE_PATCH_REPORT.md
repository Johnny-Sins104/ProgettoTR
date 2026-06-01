# PROMPT 29.4.4s-10z — LSR-v2 second paper position lifecycle audit / status sync readiness

## Scope

Adds a second-trade-aware lifecycle audit for the supervised LSR-v2 paper order opened by `29.4.4s-10y`.

This patch intentionally does not reuse the first-trade lifecycle artifact names, because those point to the first paper trade cycle. The new module reads the second-trade submit execution artifacts and paper state/status to verify that the second paper position is visible, coherent, and ready for monitoring.

## Added files

- `trading_bot/core/lsr_v2_second_trade_position_lifecycle.py`
- `trading_bot/run_lsr_v2_second_trade_position_lifecycle.py`
- `trading_bot/tests/test_lsr_v2_second_trade_position_lifecycle.py`

## Outputs

- `data/lsr_v2_second_trade_position_lifecycle_report.json`
- `data/lsr_v2_second_trade_position_lifecycle.jsonl`

## Decisions

- `LSR_V2_SECOND_TRADE_POSITION_LIFECYCLE_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_NOT_FOUND`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_STATE_INCONSISTENT`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_CLOSED_AUDIT_REQUIRED`
- `KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_OR_REENTRY_DETECTED`
- `REJECT_LSR_V2_SECOND_POSITION_LIFECYCLE_SAFETY_FAILED`

## Safety invariants

- no new order
- no new position
- no close
- no broker submit
- no broker close
- no paper state mutation
- no paper status mutation
- no re-entry
- no live
- no testnet
- no exchange broker
- third-submit/re-entry detection is explicit

## Validation

Sandbox validation:

```powershell
python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_position_lifecycle.py
# 6 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_position_lifecycle.py trading_bot/tests/test_lsr_v2_second_trade_submit_execution.py trading_bot/tests/test_lsr_v2_second_trade_submit_boundary.py trading_bot/tests/test_lsr_v2_paper_status_reconciliation.py
# 26 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_second_trade_position_lifecycle.py trading_bot/run_lsr_v2_second_trade_position_lifecycle.py
# OK
```
