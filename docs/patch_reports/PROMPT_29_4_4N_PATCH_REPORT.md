# Prompt 29.4.4n — Guarded paper-only experiment enable implementation / operator-controlled paper orders

## Scope

This patch introduces the first operator-controlled paper-only enable implementation for `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`.

It converts the final preflight candidate from 29.4.4m into a guarded runtime enable contract. The implementation is fail-closed by default and requires the full manual stack plus a dedicated operator enable/confirm pair before `paper_orders_enabled` can become true.

## Added files

- `trading_bot/core/paper_unlock_guarded_enable.py`
- `trading_bot/run_paper_unlock_guarded_enable.py`
- `trading_bot/test_paper_unlock_guarded_enable.py`
- `data/paper_unlock_guarded_enable_report.json` generated at runtime

## Controls

Required controls:

- `PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE=1`
- `PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM=CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY`
- `PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH=1`
- `PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM=ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT`
- `PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH=1`
- `PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM=ENABLE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_CANDIDATE`
- `PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS=1`
- `PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS=OPERATOR_CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ORDERS`
- requested mode must be `paper`
- live/testnet envs must be false
- exchange broker must be `blocked`

## Safety guarantees

- Live remains blocked.
- Testnet remains blocked.
- Exchange broker remains blocked.
- Automatic activation is not allowed.
- The module submits zero orders by itself.
- The module opens zero positions by itself.
- Negative scenarios remain fail-closed.

## Runtime policy

- Profile: `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`
- Entry state policy: `CONFIRMATION_ONLY`
- Allowed structure state: `CONFIRMATION`
- Blocked states: `WAIT`, `NO_STRUCTURE`, `CONFLICT`
- Map score range: `65 <= map_score < 80`
- Max positions: `1`
- Risk per trade: `0.0025`
- Max daily entries: `6`
- Max weekly entries: `30`
- Abort max consecutive losses: `3`
- Abort max drawdown: `1.0%`

## Expected validation

```cmd
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\run_paper_unlock_guarded_enable.py
```

Default expected result without operator envs:

- `status=PASS`
- `decision=GUARDED_PAPER_ENABLE_IMPLEMENTATION_READY_OPERATOR_CONTROLLED`
- `paper_orders_enabled=false`
- `paper_unlock_experiment_allowed=false`
- `operational_unlock_allowed=false`

With all operator envs correctly set, the report may show:

- `decision=GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED`
- `paper_orders_enabled=true`
- `paper_unlock_experiment_allowed=true`
- `manual_activation_allowed=true`
- `operational_unlock_allowed=false`
- `orders_submitted=0`
- `positions_opened=0`

## Next step

If local validation passes and the operator intentionally activates the paper-only controls, the next patch should be:

`29.4.4o — Paper-only runtime order audit / first controlled paper-cycle monitoring`
