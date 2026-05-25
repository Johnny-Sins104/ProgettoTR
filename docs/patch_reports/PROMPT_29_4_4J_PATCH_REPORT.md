# Prompt 29.4.4j — Guarded paper-only experiment switch implementation draft

## Status

Patch prepared as diagnostic-only switch implementation draft.

## Scope

This patch adds a fail-closed implementation draft for a future guarded paper-only experiment switch based on:

- Profile: `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`
- Activation draft: `MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT`
- Cadence: `bounded_6_daily_30_weekly_0h`
- Selected shadow entries: at least 20

## Added files

- `trading_bot/core/paper_unlock_experiment_switch_draft.py`
- `trading_bot/run_paper_unlock_experiment_switch_draft.py`
- `trading_bot/test_paper_unlock_experiment_switch_draft.py`
- `data/paper_unlock_experiment_switch_draft_report.json` generated locally by the runner

## Integration

The patch also wires the report into:

- `trading_bot/config.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/run_paper_trading.py`

CLI disable flag:

```cmd
--no-paper-unlock-experiment-switch-draft
```

## Safety

The patch does not enable execution.

Required safety fields remain false:

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `profile_activation_allowed=false`
- `automatic_activation_allowed=false`
- `manual_activation_allowed=false`

No live trading, no testnet, no exchange broker activation, no orders, no positions, no risk/threshold changes.

## Switch contract

The switch contract is a future manual-switch design only. It requires a separate activation patch and two-step confirmation.

Required future controls:

- manual enable flag
- manual confirmation value
- paper mode only
- latest activation draft recheck
- latest shadow stability recheck
- fail-closed behavior if any prerequisite is missing
- fail-closed behavior in live/testnet or exchange-broker mode

## Expected runner output

```json
{
  "status": "PASS",
  "decision": "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC",
  "switch_implementation_ready": true,
  "paper_orders_enabled": false,
  "operational_unlock_allowed": false
}
```

## Next patch

Recommended next patch:

`29.4.4k — manual paper-only switch dry-run / fail-closed preflight`

This should still be paper-only, manual, and fail-closed. It should not enable live or testnet.
