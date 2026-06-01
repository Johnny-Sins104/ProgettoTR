# Prompt 29.4.4s-10t — LSR-v2 second supervised paper trade controlled re-arm / candidate wait gate

## Scope

Adds a gate-only, non-mutating second-trade re-arm layer after `29.4.4s-10s` eligibility.

The patch can declare that the diagnostic second-trade path is re-armed only when:

- `LSR_V2_SECOND_TRADE_REARM_ENABLE=1`
- `LSR_V2_SECOND_TRADE_REARM_CONFIRMATION=I_UNDERSTAND_SECOND_PAPER_TRADE_DIAGNOSTIC_ONLY`
- second-trade eligibility has passed
- paper state and paper status are clean
- live/testnet/exchange broker remain disabled
- max orders remains exactly 1

## Added files

- `trading_bot/core/lsr_v2_second_trade_rearm_gate.py`
- `trading_bot/run_lsr_v2_second_trade_rearm_gate.py`
- `trading_bot/tests/test_lsr_v2_second_trade_rearm_gate.py`

## Outputs

- `data/lsr_v2_second_trade_rearm_gate_report.json`
- `data/lsr_v2_second_trade_rearm_gate.jsonl`

## Decisions

- `LSR_V2_SECOND_TRADE_REARM_READY_DIAGNOSTIC`
- `LSR_V2_SECOND_TRADE_CANDIDATE_WAIT_GATE_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_NOT_ENABLED`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_ELIGIBILITY_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN`
- `REJECT_LSR_V2_SECOND_TRADE_REARM_SAFETY_FAILED`

## Safety invariants

- no new order
- no new position
- no close
- no broker submit
- no broker close
- no paper state mutation
- no paper status mutation
- no live
- no testnet
- no exchange broker
- `second_trade_execute_enabled=false`
- `second_trade_submit_enabled=false`
- `paper_order_submission_enabled=false`

## Validation

Sandbox validation passed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_second_trade_rearm_gate.py
7 passed
```

Extended compile validation passed:

```text
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_second_trade_rearm_gate.py trading_bot/run_lsr_v2_second_trade_rearm_gate.py
OK
```
