# PROMPT 29.4.4s-10ad — LSR-v2 second closed paper trade final audit / realized outcome report

## Scope

Adds a non-mutating final audit for the second supervised paper-only LSR-v2 trade. The audit reconstructs the second trade lifecycle from the dedicated `second_trade_*` artifacts:

- second supervised paper submit execution
- second supervised paper close execution
- post-close `paper_state.json`
- post-close `paper_status.json`

## Outputs

- `data/lsr_v2_second_closed_trade_final_audit_report.json`
- `data/lsr_v2_second_closed_trade_final_audit.jsonl`

## Decisions

- `LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSED_TRADE_STATE_INCOMPLETE`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_RESIDUAL_OPEN_POSITION`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_PNL_RECONCILIATION_REQUIRED`
- `KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_OR_REENTRY_DETECTED`
- `REJECT_LSR_V2_SECOND_CLOSED_TRADE_AUDIT_FAILED`

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
- `third_trade_allowed=false`

## Validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_second_closed_trade_final_audit.py
python -m compileall -q trading_bot
python -m py_compile trading_bot\core\lsr_v2_second_closed_trade_final_audit.py trading_bot\run_lsr_v2_second_closed_trade_final_audit.py
```

Sandbox result:

```text
6 passed
compileall OK
py_compile OK
```
