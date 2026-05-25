# Prompt 29.4.4g — Bounded cadence expansion / rolling shadow collection

## Scope

This patch adds a diagnostic-only bounded cadence and rolling shadow collection layer after Prompt 29.4.4f.

The 29.4.4f report showed that only the unbounded `all_shadow_ceiling_99_daily_99_weekly` profile reached the minimum sample. 29.4.4g therefore tests additional bounded cadence profiles and rolling stability guards without enabling paper orders.

## Added files

- `trading_bot/core/paper_unlock_bounded_cadence.py`
- `trading_bot/run_paper_unlock_bounded_cadence.py`
- `trading_bot/test_paper_unlock_bounded_cadence.py`
- `data/paper_unlock_bounded_cadence_report.json` generated locally by the runner

## Integrated files

- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`

## Diagnostic profiles

The patch evaluates bounded cadence variants such as:

- `bounded_2_daily_14_weekly_0h`
- `bounded_3_daily_18_weekly_0h`
- `bounded_4_daily_24_weekly_0h`
- `bounded_5_daily_25_weekly_0h`
- `bounded_6_daily_30_weekly_0h`
- `bounded_4_daily_24_weekly_4h`
- `bounded_5_daily_25_weekly_4h`
- `bounded_6_daily_30_weekly_4h`

The cadence checks include daily cap, weekly cap, optional cooldown hours, equity curve in R, max consecutive losses, max drawdown, rolling window stability, holdout stability, asset concentration and side concentration.

## Safety invariants

This patch is diagnostic-only:

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `profile_activation_allowed=false`
- `orders_submitted=0`
- `positions_opened=0`
- no live
- no testnet
- no risk or threshold changes

A positive report status such as `ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC` is not an activation. It only means a bounded cadence profile can be reviewed by a later shadow sample stability patch.

## Local validation commands

```cmd
python trading_bot\test_paper_unlock_bounded_cadence.py
python trading_bot\run_paper_unlock_bounded_cadence.py
```

Compact report command:

```cmd
python -c "import json; r=json.load(open('data/paper_unlock_bounded_cadence_report.json')); d=r.get('decision',{}); b=d.get('best_bounded_cadence_variant',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'best_bounded_cadence_variant':b.get('name'),'best_selected_entries':b.get('selected_entries'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'counts':r.get('counts'),'paper_orders_enabled':r.get('paper_orders_enabled'),'paper_unlock_experiment_allowed':r.get('paper_unlock_experiment_allowed'),'operational_unlock_allowed':r.get('operational_unlock_allowed')}, indent=2))"
```

## Expected interpretation

- If the report returns `KEEP_DIAGNOSTIC`, no bounded cadence is stable enough yet.
- If it returns `ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC`, the next patch should be a shadow sample stability review, still diagnostic-only.
- No output from this patch should be used to enable paper orders, testnet or live.
