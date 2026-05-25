# Prompt 29.4.4e — Paper-only shadow experiment dry-run harness

## Scope

This patch adds a diagnostic-only shadow harness for the paper-only experiment designed in Prompt 29.4.4d.

It validates that the profile `MAP_SCORE_65_79_REPAIRED_STABILITY_V1` can be evaluated as a dry-run sequence with:

- repaired structure selector enforcement;
- `MAP_SCORE_65_79` target selection;
- entry-state-only filtering (`CONTEXT` / `CONFIRMATION`);
- WAIT / NO_STRUCTURE / CONFLICT blocking;
- daily and weekly dry-run rate limits;
- proposed abort guards;
- no paper order submission and no position opening.

## Added files

- `trading_bot/core/paper_unlock_shadow_dry_run.py`
- `trading_bot/run_paper_unlock_shadow_dry_run.py`
- `trading_bot/test_paper_unlock_shadow_dry_run.py`
- `docs/patch_reports/PROMPT_29_4_4E_PATCH_REPORT.md`

## Report

- `data/paper_unlock_shadow_dry_run_report.json`

## Safety invariants

This patch is diagnostic-only.

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `profile_activation_allowed=false`
- `orders_submitted=0`
- `positions_opened=0`
- no live mode
- no testnet mode
- no risk/threshold mutation

## Expected local validation

```cmd
python trading_bot\test_paper_unlock_shadow_dry_run.py
python trading_bot\run_paper_unlock_shadow_dry_run.py
```

Compact report:

```cmd
python -c "import json; r=json.load(open('data/paper_unlock_shadow_dry_run_report.json')); d=r.get('decision',{}); print(json.dumps({'status':r.get('status'),'decision':d.get('status'),'reason':d.get('reason'),'next_patch':d.get('next_patch'),'counts':r.get('counts'),'gate':r.get('shadow_dry_run_gate'),'equity':r.get('equity_dry_run'),'paper_orders_enabled':r.get('paper_orders_enabled'),'paper_unlock_experiment_allowed':r.get('paper_unlock_experiment_allowed'),'operational_unlock_allowed':r.get('operational_unlock_allowed')}, indent=2))"
```

## Interpretation

If the report returns `SHADOW_DRY_RUN_READY_DIAGNOSTIC`, the dry-run harness is ready but execution remains disabled. The next patch may draft a guarded paper-only activation mechanism, still with live/testnet blocked and only after explicit user approval.

If the report returns `KEEP_DIAGNOSTIC`, the dry-run guard failed and no paper activation work should proceed.
