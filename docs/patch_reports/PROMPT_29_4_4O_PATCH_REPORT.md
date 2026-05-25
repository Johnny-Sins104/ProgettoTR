# Prompt 29.4.4o — Runtime paper-order audit / first controlled paper-cycle monitoring

## Scope

This patch adds a runtime audit layer for the guarded paper-only profile:

`MAP_SCORE_65_79_REPAIRED_STABILITY_V1`

It does **not** submit orders. It makes the runtime distinction explicit between:

- legacy paper unlock profile `BTC_ONLY_40_Q60` / `PAPER_UNLOCK_29_4_4`
- guarded paper-only enable profile `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`

## Added files

- `trading_bot/core/paper_unlock_runtime_audit.py`
- `trading_bot/run_paper_unlock_runtime_audit.py`
- `trading_bot/test_paper_unlock_runtime_audit.py`
- `docs/patch_reports/PROMPT_29_4_4O_PATCH_REPORT.md`

## Runtime integration

The paper runtime now emits a separate event per symbol when enabled:

`GUARDED_PAPER_RUNTIME_AUDIT`

This event includes:

- guarded enable state from `paper_unlock_guarded_enable_report.json`
- profile name and enable name
- legacy unlock profile reference
- map score and structure state
- confirmation-only gate result
- operator enable state
- reject reasons
- diagnostic eligibility
- routing flag, always `false` in this patch

## Report

The standalone runner writes:

`data/paper_unlock_runtime_audit_report.json`

The report summarizes:

- latest completed cycle
- runtime audit event coverage
- legacy unlock event counts
- guarded profile accept/reject diagnostics
- reject reason counts
- structure state counts
- paper-only safety checks
- orders and position counts

## Safety boundaries

This patch keeps all non-paper execution blocked:

- `operational_unlock_allowed=false`
- `automatic_activation_allowed=false`
- `live_allowed=false`
- `testnet_allowed=false`
- `exchange_broker_allowed=false`
- `routing_enabled=false` in runtime audit events
- `orders_submitted_by_audit=0`

The patch may report `paper_orders_enabled=true` only if the 29.4.4n guarded enable report is active operator-controlled. That does not mean this audit module routes orders.

## Validation run in sandbox

Passed:

- `python trading_bot/test_paper_unlock_runtime_audit.py`
- `python trading_bot/test_paper_unlock_guarded_enable.py`
- `python trading_bot/test_paper_unlock_final_enable_preflight.py`
- `python trading_bot/test_paper_unlock_manual_activation_patch.py`
- `python trading_bot/test_paper_unlock_manual_switch_preflight.py`
- `python trading_bot/test_paper_unlock_experiment_switch_draft.py`
- `python trading_bot/test_paper_unlock_activation_draft.py`
- `python trading_bot/test_paper_unlock_shadow_stability_review.py`
- `python trading_bot/test_paper_unlock_bounded_cadence.py`
- `python trading_bot/test_paper_unlock_shadow_rate_calibration.py`
- `python trading_bot/test_paper_unlock_shadow_dry_run.py`
- `python trading_bot/test_paper_unlock_experiment_design.py`
- `python trading_bot/test_paper_unlock_profile_refinement.py`
- `python trading_bot/test_independent_repaired_validation.py`
- `python trading_bot/test_repaired_structure_shadow_validation.py`
- `python trading_bot/test_structure_context_repair.py`
- `python trading_bot/test_structure_filter_diagnostics.py`
- `python trading_bot/test_calibrated_structure_shadow.py`
- `python trading_bot/test_market_structure_map.py`
- `python trading_bot/test_scenario_pattern_calibration.py`

The standalone runtime audit runner on pre-patch event logs correctly returns `WARN/KEEP_DIAGNOSTIC` because old cycles do not contain `GUARDED_PAPER_RUNTIME_AUDIT` events. After installing this patch, run one new supervised paper-only cycle to generate the runtime audit events.

## Local validation commands

```cmd
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_runtime_audit.py
```

Then run one controlled paper cycle with the 29.4.4n operator controls active:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_paper_unlock_runtime_audit.py
```

Expected after the new cycle:

- runtime audit events present
- latest cycle completed
- orders remain auditable
- live/testnet remain blocked
- legacy and guarded profiles are separately visible
