# Prompt 29.4.4d — Calibrated paper-only unlock experiment design

## Scope

Diagnostic-only design layer after 29.4.4c. The patch drafts a calibrated paper-only experiment plan for `MAP_SCORE_65_79_REPAIRED_STABILITY_V1` but does **not** activate it.

## Added files

- `trading_bot/core/paper_unlock_experiment_design.py`
- `trading_bot/run_paper_unlock_experiment_design.py`
- `trading_bot/test_paper_unlock_experiment_design.py`
- `data/paper_unlock_experiment_design_report.json` generated locally

## Safety

- no live
- no testnet
- no paper orders
- no position opening
- no risk increase
- no threshold lowering
- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`

## Validation command

```cmd
python trading_bot	est_paper_unlock_experiment_design.py
python trading_botun_paper_unlock_experiment_design.py
```

Expected decision: `PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC` only if 29.4.4c profile readiness is present. This still does not enable execution.
