# Prompt 29.4.4i — Guarded paper-only activation draft / safety interlock design

## Scope

This patch adds a diagnostic-only activation draft for the paper-only profile validated through 29.5.0i, 29.5.0j, 29.4.4c, 29.4.4d, 29.4.4e, 29.4.4f, 29.4.4g and 29.4.4h.

The draft is based on:

- profile: `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`
- experiment design: `MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN`
- cadence candidate: `bounded_6_daily_30_weekly_0h`
- stability review: `SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC`

## Added files

- `trading_bot/core/paper_unlock_activation_draft.py`
- `trading_bot/run_paper_unlock_activation_draft.py`
- `trading_bot/test_paper_unlock_activation_draft.py`
- `data/paper_unlock_activation_draft_report.json` when the runner is executed locally

## Integration

The patch also integrates the activation draft in:

- `trading_bot/config.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/run_paper_trading.py`

## Safety invariant

The patch does not activate anything.

Expected report flags:

```json
{
  "operational_unlock_allowed": false,
  "paper_unlock_experiment_allowed": false,
  "paper_orders_enabled": false,
  "profile_activation_allowed": false,
  "automatic_activation_allowed": false,
  "opens_orders": false,
  "enables_live_or_testnet": false,
  "changes_thresholds": false
}
```

## Draft interlocks

The draft requires a future, separate patch before any paper-only switch can exist.
The proposed first activation is intentionally stricter than the earlier profile design:

- first activation policy: `CONFIRMATION_ONLY`
- blocked states: `WAIT`, `NO_STRUCTURE`, `CONFLICT`
- max positions: `1`
- proposed risk per paper trade: `0.0025`
- max daily entries: `6`
- max weekly entries: `30`
- abort max consecutive losses: `3`
- abort max drawdown: `1.0%`
- live/testnet: blocked
- exchange broker: blocked
- manual two-step activation: required in a future patch

## Decision states

- `GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC`

A positive decision means only that the interlock design is ready. It does not permit orders.

## Local validation

Run:

```cmd
python trading_bot\test_paper_unlock_activation_draft.py
python trading_bot\run_paper_unlock_activation_draft.py
```

Compact report:

```cmd
python -c "import json; r=json.load(open('data/paper_unlock_activation_draft_report.json')); d=r.get('decision',{}); p=r.get('stability_prerequisite',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'draft_name':d.get('draft_name'),'profile_name':d.get('profile_name'),'selected_entries':d.get('selected_entries'),'interlocks_ready':d.get('interlocks_ready'),'stability_prerequisite_ok':p.get('passes_stability_prerequisite'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'paper_orders_enabled':r.get('paper_orders_enabled'),'paper_unlock_experiment_allowed':r.get('paper_unlock_experiment_allowed'),'operational_unlock_allowed':r.get('operational_unlock_allowed'),'profile_activation_allowed':r.get('profile_activation_allowed')}, indent=2))"
```

## Next patch if local validation passes

`29.4.4j — guarded paper-only experiment switch implementation draft`, still paper-only/manual and still no live/testnet.
