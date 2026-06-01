# Prompt 30.1.0A - Commission model consolidation

## Scope

This patch consolidates the entry plus exit commission formula into
`core.commission_model.round_trip_commission`.

## Changed paths

- `trading_bot/core/commission_model.py`
- `trading_bot/main.py`
- `trading_bot/genetic_opt.py`
- `trading_bot/multi_trade_manager.py`
- `trading_bot/test_runtime_risk_io_hardening.py`

## Behavior

Closed-position fees now use:

```python
abs(size) * abs(entry_price) * rate + abs(size) * abs(exit_price) * rate
```

This keeps TP1, SL, TP2, manual close, open-position display, backtest
partials, and multi-trade close on the same helper.

## Safety contract

- No broker calls.
- No submit or close operation.
- No paper/live/testnet/exchange behavior enabled.
- No state files mutated by this patch.

## Local validation

- Python AST parse for touched files -> PASS
- `python trading_bot\test_runtime_risk_io_hardening.py` -> PASS
- `rg` check for old duplicated entry-only commission patterns in touched runtime files -> no matches
- `python tools\run_checks.py --no-pytest` -> PASS, 657 Python files parsed, 0 syntax errors

## Next step

The next consolidation pass should align commission-aware sizing in risk and
paper engines with this helper, using dedicated fixtures for expected risk per
unit and net PnL.
