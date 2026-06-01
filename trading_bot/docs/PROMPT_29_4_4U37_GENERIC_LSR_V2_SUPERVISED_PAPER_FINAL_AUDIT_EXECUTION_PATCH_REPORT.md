# Prompt 29.4.4u-37 — Generic LSR-v2 supervised paper final audit execution

## Scope
Adds a controlled, paper-only final-audit execution gate/model that consumes the u-36 final-audit execution scaffold report.

## Files
- `trading_bot/core/lsr_v2_generic_supervised_paper_final_audit_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_final_audit_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_final_audit_execution.py`

## Expected validation state
The patch returns `PASS` with decision `LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_READY` when u-36 is ready and source markers are present.

## Safety
No final audit runtime execution occurs. No postmortem, submit, close, broker call, scheduler start, Telegram/network send, or paper state/status mutation is allowed. The model remains blocked until real submit/close receipts, closed paper position, realized-PnL reconciliation/write, runtime values, and explicit operator gates exist.

## Next patch
`29.4.4u-38 — Generic LSR-v2 supervised paper postmortem preflight`.
