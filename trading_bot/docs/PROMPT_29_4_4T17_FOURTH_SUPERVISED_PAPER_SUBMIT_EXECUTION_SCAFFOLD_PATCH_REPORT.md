# PROMPT 29.4.4t-17 — LSR-v2 fourth supervised paper-only submit execution scaffold

## Scope

This patch adds a fail-closed supervised paper-only submit execution scaffold for the fourth LSR-v2 trade.
It consumes the validated `29.4.4t-16` submit preflight and reports whether a future paper submit execution could be allowed.

Current validated state has no fourth-specific route candidate and no `paper_order_intent`; therefore this patch must return a no-order diagnostic and submit nothing.

## Files

- `trading_bot/core/lsr_v2_fourth_trade_submit_execution.py`
- `trading_bot/run_lsr_v2_fourth_trade_submit_execution.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_submit_execution.py`

## Safety guarantees

- No broker submit call when `paper_order_intent_ready=false`.
- No route execution.
- No position open.
- No position close.
- No paper state mutation.
- No paper status mutation.
- No Telegram network send.
- No scheduler start.
- No live/testnet/exchange broker.
- Operator controls are modeled but do not cause a broker call in this scaffold.

## Expected local output in current state

```text
status = PASS
decision = LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY
paper_order_intent_ready = false
would_submit = false
broker_submit_called = false
orders_submitted_by_submit_execution = 0
positions_opened_by_submit_execution = 0
submit_execution_diagnostic = NO_ORDER_SUBMIT_EXECUTION_DIAGNOSTIC
```
