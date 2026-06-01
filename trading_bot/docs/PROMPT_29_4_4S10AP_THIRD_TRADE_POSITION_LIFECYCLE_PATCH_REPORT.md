# Prompt 29.4.4s-10ap — LSR-v2 third paper trade position lifecycle

## Scope

Adds an audit-only lifecycle layer for the third supervised LSR-v2 paper trade after `29.4.4s-10ao` submit execution.

## Files

- `trading_bot/core/lsr_v2_third_trade_position_lifecycle.py`
- `trading_bot/run_lsr_v2_third_trade_position_lifecycle.py`
- `trading_bot/tests/test_lsr_v2_third_trade_position_lifecycle.py`

## Safety

- No order submission.
- No position opening.
- No position closing.
- No broker call.
- No paper state/status mutation.
- Live, testnet, exchange broker and operational unlock remain disabled.

## Expected decision

When the third submit execution is PASS and paper state/status contain exactly one matching open third LSR-v2 position:

```text
LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY
```

The next step is the third open-position monitor.
