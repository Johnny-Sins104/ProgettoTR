# Prompt 29.4.4m — Final manual paper-only enable preflight / paper-order activation candidate

## Scope
Adds a final manual paper-only enable preflight for `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`.

The patch validates the full chain from 29.4.4l and produces a paper-order activation candidate, but it does not submit orders and does not enable live/testnet.

## Added files

- `trading_bot/core/paper_unlock_final_enable_preflight.py`
- `trading_bot/run_paper_unlock_final_enable_preflight.py`
- `trading_bot/test_paper_unlock_final_enable_preflight.py`
- `data/paper_unlock_final_enable_preflight_report.json` generated locally

## Safety

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `automatic_activation_allowed=false`
- `manual_activation_allowed=false`
- `opens_orders=false`
- live/testnet/exchange broker blocked

## Validation

Run:

```cmd
python trading_bot	est_paper_unlock_final_enable_preflight.py
python trading_botun_paper_unlock_final_enable_preflight.py
```

Expected decision: `FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC` if 29.4.4l prerequisites are present.
