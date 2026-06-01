# Prompt 29.4.4s-10ag — LSR-v2 third supervised paper-trade eligibility gate

## Scope

Adds a read-only eligibility gate for evaluating a third supervised paper-only LSR-v2 trade after:

- two supervised paper trades have been opened and closed;
- the two-trade postmortem has passed;
- the post-two-trade observation has passed with at least 4h and 8h cycle coverage;
- no third submit/re-entry, residual position, or pending order is present;
- the Telegram SL/TP position monitor bridge is installed and protected by stale-open guard.

## Safety

The gate does not submit orders, close positions, open positions, mutate `paper_state.json`, mutate `paper_status.json`, call a broker, or enable live/testnet/exchange broker behavior.

## Expected local decision

With the validated 8h observation (`completed_observation_cycles=85`), expected decision:

```text
LSR_V2_THIRD_PAPER_TRADE_ELIGIBILITY_PASS
```

but still:

```text
third_trade_submit_enabled=false
third_trade_execute_enabled=false
paper_order_submission_enabled=false
orders_submitted_by_third_trade_gate=0
positions_opened_by_third_trade_gate=0
```

## Validation

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_third_trade_eligibility_gate.py
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_third_trade_eligibility_gate.py trading_bot/run_lsr_v2_third_trade_eligibility_gate.py
```
