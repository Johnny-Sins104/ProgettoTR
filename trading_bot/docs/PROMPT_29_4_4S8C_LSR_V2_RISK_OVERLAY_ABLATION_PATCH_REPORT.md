# Prompt 29.4.4s-8c — LSR-v2 risk overlay ablation / drawdown control preflight

## Scope

Adds a diagnostic-only risk-overlay ablation layer for the locked LSR-v2 profile:

`LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`

The patch consumes `data/lsr_v2_sample_expansion_trades.jsonl` and, when present, `data/lsr_v2_cost_drawdown_attribution_report.json`. It compares non-operative risk overlays intended to reduce drawdown, loss streaks and cost-degradation exposure.

## Added files

- `trading_bot/core/lsr_v2_risk_overlay_ablation.py`
- `trading_bot/run_lsr_v2_risk_overlay_ablation.py`
- `trading_bot/tests/test_lsr_v2_risk_overlay_ablation.py`
- `trading_bot/docs/PROMPT_29_4_4S8C_LSR_V2_RISK_OVERLAY_ABLATION_PATCH_REPORT.md`

## Reports

- `data/lsr_v2_risk_overlay_ablation_report.json`
- `data/lsr_v2_risk_overlay_variants.json`
- `data/lsr_v2_risk_overlay_trades.jsonl`
- `data/lsr_v2_risk_overlay_selection_report.json`

## Overlay families

The audit evaluates:

- `max_consecutive_loss_pause_3/5/7`
- `rolling_drawdown_pause_5R/10R/15R`
- `daily_or_session_loss_cap_2R/3R`
- oracle severe-cost / break-even filters, explicitly marked `oracle_overlay=true`
- realized expected-R group filters, explicitly marked `oracle_overlay=true`
- asset/timeframe and side risk caps

Oracle overlays are diagnostic only and are not deployable until replaced by an ex-ante proxy.

## Safety constraints

The patch is offline and diagnostic-only:

- no live trading
- no testnet trading
- no exchange broker
- no broker call
- no order submission
- no position opening
- no paper-state mutation
- no threshold lowering
- `promotion_ready=false`

## Validation

Expected local validation commands:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_risk_overlay_ablation.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_risk_overlay_ablation.py --data-dir data
```

## Possible decisions

- `LSR_V2_RISK_OVERLAY_RESEARCH_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_OVERLAY_INSUFFICIENT`
- `KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH`
- `KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY`
- `REJECT_LSR_V2_OPERATIONALLY_UNSTABLE`
- `KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_NO_TRADES`
- `KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_ERROR`
