# PROMPT 29.4.4s-10v — LSR-v2 second trade paper broker handoff dry-run / submit preflight

## Scope

Adds a second-trade-specific paper broker handoff dry-run after `29.4.4s-10u`.
The layer converts `LSR_V2_SECOND_TRADE_ORDER_INTENT_PREFLIGHT` into a broker-compatible diagnostic payload.

## Files

- `trading_bot/core/lsr_v2_second_trade_handoff_dry_run.py`
- `trading_bot/run_lsr_v2_second_trade_handoff_dry_run.py`
- `trading_bot/tests/test_lsr_v2_second_trade_handoff_dry_run.py`

## Outputs

- `data/lsr_v2_second_trade_handoff_dry_run_report.json`
- `data/lsr_v2_second_trade_handoff_dry_run.jsonl`

## Safety

- No broker submit.
- No paper order submission.
- No position opening.
- No paper state/status mutation.
- No live/testnet/exchange broker.
- `second_trade_execute_enabled=false` and `second_trade_submit_enabled=false` always.

## Expected pass decision

`LSR_V2_SECOND_TRADE_HANDOFF_DRY_RUN_READY`
