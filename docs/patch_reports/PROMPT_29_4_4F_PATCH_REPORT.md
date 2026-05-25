# Prompt 29.4.4f — Shadow dry-run sample expansion / rate-limit calibration

## Scope

Diagnostic-only follow-up to 29.4.4e. The prior dry-run harness worked but selected only seven shadow entries under the conservative `1 daily / 5 weekly` cadence. This patch compares bounded rate-limit profiles to determine whether the validated `MAP_SCORE_65_79_REPAIRED_STABILITY_V1` profile can reach a sufficient dry-run sample without violating guardrails.

## Added files

- `trading_bot/core/paper_unlock_shadow_rate_calibration.py`
- `trading_bot/run_paper_unlock_shadow_rate_calibration.py`
- `trading_bot/test_paper_unlock_shadow_rate_calibration.py`
- `data/paper_unlock_shadow_rate_calibration_report.json` generated locally

## Rate profiles audited

- `current_1_daily_5_weekly`
- `weekly_relaxed_1_daily_10_weekly`
- `balanced_2_daily_10_weekly`
- `expanded_3_daily_15_weekly`
- `sample_expanded_4_daily_20_weekly`
- `all_shadow_ceiling_99_daily_99_weekly` as diagnostic ceiling only

## Safety invariants

- No orders
- No live/testnet
- No paper experiment activation
- No threshold/risk mutation
- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`

## Local validation

Run:

```cmd
python trading_bot	est_paper_unlock_shadow_rate_calibration.py
python trading_botun_paper_unlock_shadow_rate_calibration.py
```

Compact report:

```cmd
python -c "import json; r=json.load(open('data/paper_unlock_shadow_rate_calibration_report.json')); d=r.get('decision',{}); b=d.get('best_rate_variant',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'best_rate_variant':b.get('name'),'best_selected_entries':b.get('selected_entries'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'counts':r.get('counts'),'paper_orders_enabled':r.get('paper_orders_enabled'),'paper_unlock_experiment_allowed':r.get('paper_unlock_experiment_allowed'),'operational_unlock_allowed':r.get('operational_unlock_allowed')}, indent=2))"
```
