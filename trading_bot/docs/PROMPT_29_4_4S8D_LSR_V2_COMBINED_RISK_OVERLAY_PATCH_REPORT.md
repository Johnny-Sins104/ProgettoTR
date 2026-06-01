# Prompt 29.4.4s-8d — LSR-v2 combined risk overlay / operational viability preflight

## Scope

Adds a diagnostic-only combined risk-overlay preflight for the locked LSR-v2 research profile:

`LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`

Locked variant:

`retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24`

This patch builds on 29.4.4s-8c, where the best single non-oracle overlay was `max_consecutive_loss_pause_3`, but remained insufficient because max consecutive losses stayed above limit.

## Files added

- `trading_bot/core/lsr_v2_combined_risk_overlay.py`
- `trading_bot/run_lsr_v2_combined_risk_overlay.py`
- `trading_bot/tests/test_lsr_v2_combined_risk_overlay.py`
- `trading_bot/docs/PROMPT_29_4_4S8D_LSR_V2_COMBINED_RISK_OVERLAY_PATCH_REPORT.md`

## Reports produced

- `data/lsr_v2_combined_risk_overlay_report.json`
- `data/lsr_v2_combined_risk_overlay_variants.json`
- `data/lsr_v2_combined_risk_overlay_trades.jsonl`
- `data/lsr_v2_operational_viability_preflight_report.json`

## Overlay combinations tested

The patch tests deterministic, non-oracle combinations including:

- `combo_loss3_dd10`
- `combo_loss3_dd15`
- `combo_loss3_dd10_asset_cap`
- `combo_loss3_dd10_side_cap`
- `combo_loss3_session_loss_2R`
- `combo_loss3_session_loss_3R`
- `combo_loss3_dd10_cooldown_12`
- `combo_loss3_dd10_cooldown_24`
- `combo_loss3_dd10_asset_side_cap`
- `combo_loss3_dd10_session_cap_cooldown`

Additional nearby controls are included to avoid a too-narrow search around one combination.

## Minimum validity criteria

A combined overlay is valid only if all of these are true:

- `max_drawdown_r <= 15R` by default
- `max_consecutive_losses <= 10` by default
- `profit_retention_ratio >= 0.50`
- `avg_r_post_cost > 0`
- `sum_r_post_cost > 0`
- `cost_degradation_ratio <= 1.25`
- `severe_positive_ratio >= 0.60`
- `trades_kept >= 300` by default
- `oracle_overlay=false`

## Decisions

Possible top-level decisions:

- `LSR_V2_COMBINED_OVERLAY_RESEARCH_READY`
- `LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS`
- `KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_INSUFFICIENT`
- `KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH`
- `KEEP_DIAGNOSTIC_LSR_V2_LOSS_STREAK_REMAINS_HIGH`
- `KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY`
- `REJECT_LSR_V2_OPERATIONALLY_UNSTABLE`
- `KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_NO_TRADES`
- `KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_ERROR`

## Safety constraints

This patch is diagnostic-only:

- no live
- no testnet
- no exchange broker
- no broker calls
- no order submission
- no position opening
- no paper state mutation
- no threshold lowering
- no runtime routing
- `promotion_ready=false`

Even if `LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS` is returned, this is not a permission to execute. A separate promotion-gate patch is still required.

## Validation run in sandbox

```bash
python -m pytest -q trading_bot/tests/test_lsr_v2_combined_risk_overlay.py
# 5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_combined_risk_overlay.py trading_bot/tests/test_lsr_v2_risk_overlay_ablation.py trading_bot/tests/test_lsr_v2_cost_drawdown_attribution.py trading_bot/tests/test_lsr_v2_robustness_validation.py trading_bot/tests/test_lsr_v2_sample_expansion.py trading_bot/tests/test_lsr_v2_locked_profile.py
# 30 passed

python -m compileall -q trading_bot
# OK
```

Smoke test with no trade file returns a safe warning:

`KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_NO_TRADES`
