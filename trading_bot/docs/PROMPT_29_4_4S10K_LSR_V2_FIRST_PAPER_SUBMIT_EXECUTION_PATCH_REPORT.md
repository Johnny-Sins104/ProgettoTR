# Prompt 29.4.4s-10k — LSR-v2 first supervised paper-only submit / single-order execution boundary

## Scope

This patch adds the first supervised LSR-v2 paper-only submit execution boundary. It is disabled by default and can submit at most one order only when all upstream LSR-v2 gates are already satisfied and the operator provides explicit execution arming.

## Added files

- `core/lsr_v2_supervised_paper_submit_execution.py`
- `run_lsr_v2_supervised_paper_submit_execution.py`
- `tests/test_lsr_v2_supervised_paper_submit_execution.py`

## Required manual execution controls

- `LSR_V2_PAPER_SUBMIT_ARM=1`
- `LSR_V2_PAPER_SUBMIT_CONFIRMATION=I_UNDERSTAND_SINGLE_PAPER_ORDER`
- `LSR_V2_PAPER_SUBMIT_EXECUTE=1`
- `LSR_V2_PAPER_SUBMIT_EXECUTE_CONFIRMATION=I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY`
- `LSR_V2_PAPER_SUBMIT_MAX_ORDERS=1`

## Safety invariants

- Live execution remains disabled.
- Testnet execution remains disabled.
- Exchange broker execution remains disabled.
- `operational_unlock_allowed=false`.
- Single-order cap is enforced.
- Paper state must be clean before submit.
- No retry loop, no batch orders, no automatic activation.

## Outputs

- `data/lsr_v2_supervised_paper_submit_execution_report.json`
- `data/lsr_v2_supervised_paper_submit_execution.jsonl`

## Expected decisions

- `KEEP_DIAGNOSTIC_LSR_V2_EXECUTION_NOT_ARMED`
- `KEEP_DIAGNOSTIC_LSR_V2_EXECUTION_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_PREFLIGHT_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_PAPER_STATE_NOT_CLEAN`
- `KEEP_DIAGNOSTIC_LSR_V2_PAPER_SUBMITTER_NOT_AVAILABLE`
- `LSR_V2_SINGLE_PAPER_ORDER_EXECUTED`
- `REJECT_LSR_V2_EXECUTION_SAFETY_FAILED`

## Validation

Sandbox validation:

```bash
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_submit_execution.py
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_submit_execution.py trading_bot/tests/test_lsr_v2_supervised_paper_submit.py trading_bot/tests/test_lsr_v2_supervised_paper_submit_preflight.py trading_bot/tests/test_lsr_v2_paper_broker_handoff_dry_run.py trading_bot/tests/test_lsr_v2_order_intent_audit.py
python -m compileall -q trading_bot
```
