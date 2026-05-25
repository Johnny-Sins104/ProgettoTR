# Prompt 29.5.0j — Independent repaired validation stability / walk-forward guard

## Scope

This patch adds a diagnostic-only stability guard after Prompt 29.5.0i. The previous patch found the first aggregate diagnostic candidate, `map_score_65_79_all`, but this patch does **not** unlock trading. It validates whether that candidate is stable enough to justify a later paper-unlock refinement design.

## Added files

- `trading_bot/core/independent_repaired_validation.py`
- `trading_bot/run_independent_repaired_validation.py`
- `trading_bot/test_independent_repaired_validation.py`
- `data/independent_repaired_validation_report.json` generated locally by the runner

## What it validates

- Aggregate `MAP_SCORE_65_79` candidate from 29.5.0i
- Chronological walk-forward folds
- Recent holdout split
- Asset and side concentration
- Target rows by state, confirmation summary, price location and structure bias
- Comparison variants: repaired entry-state, confirmation-only, clean subset, no-WAIT/no-CONFLICT, BOS subsets, WAIT/NO_STRUCTURE blocked subsets

## Safety invariants

- No orders
- No live trading
- No testnet
- No paper unlock
- No risk change
- No threshold lowering
- No operational use of `MAP_SCORE_65_79`

Even if the report returns `STABILITY_CANDIDATE_DIAGNOSTIC`, operational unlock remains false.

## Local validation commands

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\test_independent_repaired_validation.py
python trading_bot\run_independent_repaired_validation.py
```

Then inspect a compact decision summary:

```cmd
python -c "import json; r=json.load(open('data/independent_repaired_validation_report.json')); d=r.get('decision',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'counts':r.get('counts'),'walk_forward':(r.get('walk_forward') or {}).get('stability_checks'),'concentration':(r.get('concentration') or {}).get('checks')}, indent=2))"
```

## Expected interpretation

- `KEEP_DIAGNOSTIC`: no paper-unlock refinement; inspect weak holdout/folds or collect more repaired rows.
- `STABILITY_CANDIDATE_DIAGNOSTIC`: the profile can be considered for a later paper-unlock refinement **design**, but still cannot open paper/live/testnet orders.
