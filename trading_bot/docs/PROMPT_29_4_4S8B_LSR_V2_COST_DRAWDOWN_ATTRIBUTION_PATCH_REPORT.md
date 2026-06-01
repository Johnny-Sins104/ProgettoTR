# PROMPT 29.4.4s-8b — LSR-v2 cost degradation and drawdown attribution audit

## Scope

Diagnostic-only attribution layer for the locked LSR-v2 profile:

`LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`

The patch consumes `data/lsr_v2_sample_expansion_trades.jsonl` and, when available, `data/lsr_v2_robustness_validation_report.json`. It explains the remaining robustness blockers from 29.4.4s-8:

- cost degradation under the severe cost model;
- excessive primary/conservative drawdown;
- asset/timeframe/side/window/exit-reason loss concentration;
- risk overlay preflight candidates, kept strictly diagnostic.

## Added files

- `trading_bot/core/lsr_v2_cost_drawdown_attribution.py`
- `trading_bot/run_lsr_v2_cost_drawdown_attribution.py`
- `trading_bot/tests/test_lsr_v2_cost_drawdown_attribution.py`
- `trading_bot/docs/PROMPT_29_4_4S8B_LSR_V2_COST_DRAWDOWN_ATTRIBUTION_PATCH_REPORT.md`

## Output files

- `data/lsr_v2_cost_drawdown_attribution_report.json`
- `data/lsr_v2_cost_degradation_attribution_report.json`
- `data/lsr_v2_drawdown_attribution_report.json`
- `data/lsr_v2_drawdown_segments.jsonl`
- `data/lsr_v2_risk_overlay_preflight_report.json`

## Decisions

- `LSR_V2_COST_DRAWDOWN_ATTRIBUTION_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_CONFIRMED`
- `KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_CLUSTERED`
- `KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_REQUIRED`
- `REJECT_LSR_V2_OPERATIONALLY_UNSTABLE`
- `KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_NO_TRADES`
- `KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_ERROR`

## Safety

The patch is forensic and offline only:

- no live trading;
- no testnet;
- no exchange broker;
- no broker call;
- no order submission;
- no position opening;
- no paper state mutation;
- no threshold lowering;
- `promotion_ready=false` by design.

Risk overlays in the report are diagnostic preflight simulations only. They are not activated in runtime and are not used to route or submit orders.

## Sandbox validation

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_cost_drawdown_attribution.py
5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_cost_drawdown_attribution.py trading_bot/tests/test_lsr_v2_robustness_validation.py trading_bot/tests/test_lsr_v2_sample_expansion.py trading_bot/tests/test_lsr_v2_locked_profile.py trading_bot/tests/test_lsr_v2_execution_ablation.py
25 passed

python -m compileall -q trading_bot
compileall OK
```

Smoke test without trade files returns safe WARN:

```text
KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_NO_TRADES
orders_submitted_by_lsr_v2_cost_drawdown_attribution=0
positions_opened_by_lsr_v2_cost_drawdown_attribution=0
promotion_ready=false
```
