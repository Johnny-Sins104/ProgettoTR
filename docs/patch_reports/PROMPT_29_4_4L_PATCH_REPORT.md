# Prompt 29.4.4l — Explicit manual paper-only activation patch draft

## Scope

Adds a draft-only explicit manual paper-only activation patch contract for `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`.

## Safety

- No orders are submitted.
- Paper orders remain disabled.
- Live and testnet are blocked.
- Exchange broker remains blocked.
- Automatic activation is not allowed.
- Manual activation is not allowed in this patch; it is only simulated for a future patch context.

## New files

- `trading_bot/core/paper_unlock_manual_activation_patch.py`
- `trading_bot/run_paper_unlock_manual_activation_patch.py`
- `trading_bot/test_paper_unlock_manual_activation_patch.py`
- `data/paper_unlock_manual_activation_patch_report.json` generated locally

## Validation

Run:

```cmd
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\run_paper_unlock_manual_activation_patch.py
```

Expected decision: `EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT_READY_DIAGNOSTIC` if 29.4.4k preflight is present and valid.
