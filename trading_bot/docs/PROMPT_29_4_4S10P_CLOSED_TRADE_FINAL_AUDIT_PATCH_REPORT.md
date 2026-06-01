# PROMPT 29.4.4s-10p — LSR-v2 closed paper trade final audit / realized outcome report

## Scope

Adds a read-only final audit for the first completed LSR-v2 paper-only trade lifecycle.

The audit reconstructs:

1. supervised paper submit execution;
2. open position monitor / TP diagnostic;
3. supervised close preflight;
4. supervised paper close execution;
5. post-close lifecycle and paper state/status consistency.

## Added files

```text
trading_bot/core/lsr_v2_closed_trade_final_audit.py
trading_bot/run_lsr_v2_closed_trade_final_audit.py
trading_bot/tests/test_lsr_v2_closed_trade_final_audit.py
trading_bot/docs/PROMPT_29_4_4S10P_CLOSED_TRADE_FINAL_AUDIT_PATCH_REPORT.md
PATCH_29_4_4S10P_MANIFEST.txt
```

## Outputs

```text
data/lsr_v2_closed_trade_final_audit_report.json
data/lsr_v2_closed_trade_final_audit.jsonl
```

## Decisions

```text
LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS
KEEP_DIAGNOSTIC_LSR_V2_CLOSED_TRADE_STATE_INCOMPLETE
KEEP_DIAGNOSTIC_LSR_V2_RESIDUAL_OPEN_POSITION
KEEP_DIAGNOSTIC_LSR_V2_PNL_RECONCILIATION_REQUIRED
KEEP_DIAGNOSTIC_LSR_V2_EXTRA_SUBMIT_OR_REENTRY_DETECTED
REJECT_LSR_V2_CLOSED_TRADE_AUDIT_FAILED
```

## Safety invariants

The audit is strictly read-only:

```text
paper_state_modified_by_final_audit=false
paper_status_modified_by_final_audit=false
broker_submit_called_by_final_audit=false
broker_close_called_by_final_audit=false
orders_submitted_by_final_audit=0
positions_opened_by_final_audit=0
positions_closed_by_final_audit=0
automatic_reentry_enabled=false
automatic_close_enabled=false
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
operational_unlock_allowed=false
promotion_ready=false
```

## Validation performed in sandbox

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_closed_trade_final_audit.py
6 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_closed_trade_final_audit.py trading_bot/run_lsr_v2_closed_trade_final_audit.py
OK
```

## Notes

The final audit deliberately does not open, close, submit, retry, or re-enter. It only reconciles reports and state after the supervised close has already completed.
