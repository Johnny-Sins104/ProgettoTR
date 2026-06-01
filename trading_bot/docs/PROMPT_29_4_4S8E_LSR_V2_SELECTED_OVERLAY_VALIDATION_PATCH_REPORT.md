# PROMPT 29.4.4s-8e — LSR-v2 selected overlay robustness validation / anti-overfit lock

## Scope

Adds a diagnostic-only validation suite for the locked LSR-v2 research profile with the selected non-oracle combined risk overlay:

- Strategy profile: `LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`
- Locked variant: `retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24`
- Selected overlay: `combo_loss3_dd10_side_cap`

The patch validates the selected overlay in isolation rather than reranking the full overlay search space. This is an anti-overfit preflight before a separate future promotion gate.

## Added files

```text
trading_bot/core/lsr_v2_selected_overlay_validation.py
trading_bot/run_lsr_v2_selected_overlay_validation.py
trading_bot/tests/test_lsr_v2_selected_overlay_validation.py
trading_bot/docs/PROMPT_29_4_4S8E_LSR_V2_SELECTED_OVERLAY_VALIDATION_PATCH_REPORT.md
```

## Outputs

```text
data/lsr_v2_selected_overlay_validation_report.json
data/lsr_v2_selected_overlay_walk_forward_report.json
data/lsr_v2_selected_overlay_oos_report.json
data/lsr_v2_selected_overlay_bootstrap_report.json
data/lsr_v2_selected_overlay_trades.jsonl
```

## Inputs

Default inputs:

```text
data/lsr_v2_combined_risk_overlay_trades.jsonl
data/lsr_v2_sample_expansion_trades.jsonl
```

The module takes kept primary-cost trades from the selected overlay rows and pairs them with severe-cost trades from the sample-expansion rows using the same candidate/dataset identity.

## Validation criteria

Default criteria:

```text
selected primary trades >= 300
walk_forward_positive_ratio >= 0.55
oos_pass = true
bootstrap_positive_ratio >= 0.60
bootstrap_median_avg_r > 0
max_drawdown_r <= 15R
max_consecutive_losses <= 10
cost_degradation_ratio <= 1.25
severe_positive_ratio >= 0.60
asset/timeframe/side stability OK
overlay_oracle = false
```

## Decisions

```text
LSR_V2_SELECTED_OVERLAY_VALIDATION_PASS
LSR_V2_SELECTED_OVERLAY_READY_FOR_PROMOTION_GATE
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_WALK_FORWARD_UNSTABLE
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_OOS_FAILED
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_BOOTSTRAP_FRAGILE
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_COST_DEGRADATION_FAILED
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_DRAWDOWN_FAILED
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_LOSS_STREAK_FAILED
REJECT_LSR_V2_SELECTED_OVERLAY_VALIDATION_FAILED
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_NO_TRADES
KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_VALIDATION_ERROR
```

## Safety invariants

This patch is diagnostic-only:

```text
no live
no testnet
no exchange broker
no broker call
no order submission
no position opening
no paper state mutation
no threshold lowering
promotion_ready=false
```

Even if the selected overlay passes, the patch does not authorize execution. A separate strategy promotion gate is required before any paper-supervised path.

## Sandbox validation

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_selected_overlay_validation.py
# 5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_selected_overlay_validation.py trading_bot/tests/test_lsr_v2_combined_risk_overlay.py trading_bot/tests/test_lsr_v2_risk_overlay_ablation.py trading_bot/tests/test_lsr_v2_cost_drawdown_attribution.py trading_bot/tests/test_lsr_v2_robustness_validation.py
# 25 passed

python -m compileall -q trading_bot
# OK
```

A smoke run with no trade files returns `KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_NO_TRADES`, creates safe empty reports, and keeps all execution counters at zero.
