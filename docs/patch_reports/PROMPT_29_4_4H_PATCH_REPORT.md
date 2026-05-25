# Prompt 29.4.4h — Shadow sample stability review

## Scope

Diagnostic-only review of the bounded cadence sample produced by Prompt 29.4.4g.
The patch validates whether `bounded_6_daily_30_weekly_0h` / best bounded cadence
sample is stable enough to justify a future guarded paper-only activation draft.

## Added files

- `trading_bot/core/paper_unlock_shadow_stability_review.py`
- `trading_bot/run_paper_unlock_shadow_stability_review.py`
- `trading_bot/test_paper_unlock_shadow_stability_review.py`
- `data/paper_unlock_shadow_stability_review_report.json` when the runner is executed

## Validation checks

The report reviews:

- bounded cadence prerequisite from 29.4.4g
- aggregate sample size / expectancy / loss / time-exit
- equity dry-run max consecutive losses and max drawdown
- rolling-window stability
- recent holdout stability
- asset and side concentration
- temporal dispersion across days/weeks
- state / confirmation / location breakdown

## Safety invariants

This patch never enables execution:

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `profile_activation_allowed=false`
- `orders_submitted=0`
- `positions_opened=0`

Even `SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC` is not an activation. It only
permits consideration of a separate, future guarded paper-only activation draft.

## Local validation commands

```cmd
python trading_bot\test_paper_unlock_shadow_stability_review.py
python trading_bot\run_paper_unlock_shadow_stability_review.py
```

Compact report reader:

```cmd
python -c "import json; r=json.load(open('data/paper_unlock_shadow_stability_review_report.json')); d=r.get('decision',{}); c=r.get('stability_checks',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'best_stability_review_variant':d.get('best_stability_review_variant'),'selected_entries':d.get('selected_entries'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'counts':r.get('counts'),'sample_ok':c.get('sample_ok'),'rolling_window_ok':c.get('rolling_window_ok'),'holdout_ok':c.get('holdout_ok'),'concentration_ok':c.get('concentration_ok'),'temporal_dispersion_ok':c.get('temporal_dispersion_ok'),'paper_orders_enabled':r.get('paper_orders_enabled'),'paper_unlock_experiment_allowed':r.get('paper_unlock_experiment_allowed'),'operational_unlock_allowed':r.get('operational_unlock_allowed')}, indent=2))"
```
