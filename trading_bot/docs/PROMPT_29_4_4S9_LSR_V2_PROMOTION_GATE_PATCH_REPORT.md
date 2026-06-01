# PROMPT 29.4.4s-9 — LSR-v2 promotion gate / paper-supervised readiness preflight

## Scope

Adds a diagnostic-only promotion gate for the locked LSR-v2 profile:

- Strategy profile: `LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`
- Variant: `retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24`
- Selected non-oracle overlay: `combo_loss3_dd10_side_cap`

The gate reads prior LSR-v2 reports and emits one consolidated paper-supervised-candidate decision.
It does not execute orders, route signals, call brokers, mutate paper state, or enable live/testnet/exchange paths.

## Added files

- `trading_bot/core/lsr_v2_promotion_gate.py`
- `trading_bot/run_lsr_v2_promotion_gate.py`
- `trading_bot/tests/test_lsr_v2_promotion_gate.py`
- `trading_bot/docs/PROMPT_29_4_4S9_LSR_V2_PROMOTION_GATE_PATCH_REPORT.md`

## Required input reports

The runner expects these reports in `data/` unless explicit CLI overrides are provided:

- `lsr_v2_selected_overlay_validation_report.json`
- `lsr_v2_selected_overlay_walk_forward_report.json`
- `lsr_v2_selected_overlay_oos_report.json`
- `lsr_v2_selected_overlay_bootstrap_report.json`
- `lsr_v2_combined_risk_overlay_report.json`
- `lsr_v2_operational_viability_preflight_report.json`
- `lsr_v2_sample_expansion_report.json`

## Output

- `data/lsr_v2_promotion_gate_report.json`

## Pass decision

The pass decision is:

```text
LSR_V2_PAPER_SUPERVISED_CANDIDATE
```

When this decision is emitted, the report sets:

```json
{
  "paper_supervised_candidate": true,
  "paper_supervised_readiness_preflight_pass": true,
  "promotion_ready": false,
  "execution_enabled": false,
  "routing_enabled": false,
  "paper_order_submission_enabled": false
}
```

This is a readiness decision only, not an execution switch.

## Blocking decisions

- `KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_BLOCKED`
- `KEEP_DIAGNOSTIC_LSR_V2_REPORTS_INCOMPLETE`
- `REJECT_LSR_V2_PROMOTION_GATE_FAILED`
- `KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_GATE_ERROR`

## Core criteria

The gate requires:

- selected overlay validation ready for promotion gate;
- selected overlay is non-oracle;
- selected primary trades >= 300;
- positive primary avg R and sum R;
- max drawdown <= 15R;
- max consecutive losses <= 10;
- walk-forward stable and positive ratio >= 0.55;
- OOS pass and positive OOS R;
- bootstrap pass and positive ratio >= 0.60;
- cost degradation non-destructive and ratio <= 1.25;
- severe positive ratio >= 0.60;
- asset, timeframe, and side stability OK;
- combined overlay operational preflight pass;
- sample expansion ready for walk-forward;
- no input-report safety leakage.

## Safety invariants

The promotion gate hard-codes these output invariants:

- `orders_submitted_by_lsr_v2_promotion_gate=0`
- `positions_opened_by_lsr_v2_promotion_gate=0`
- `broker_submit_called=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `execution_enabled=false`
- `routing_enabled=false`
- `paper_order_submission_enabled=false`
- `audit_only=true`

It also scans input reports for nonzero submitted/opened/broker/live/testnet/exchange flags and rejects the gate on safety violation.

## Validation

Sandbox validation performed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_promotion_gate.py
5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_promotion_gate.py trading_bot/tests/test_lsr_v2_selected_overlay_validation.py trading_bot/tests/test_lsr_v2_combined_risk_overlay.py trading_bot/tests/test_lsr_v2_robustness_validation.py
20 passed

python -m compileall -q trading_bot
compileall OK
```

Smoke tests:

- missing reports -> `KEEP_DIAGNOSTIC_LSR_V2_REPORTS_INCOMPLETE`;
- synthetic valid reports -> `LSR_V2_PAPER_SUPERVISED_CANDIDATE`;
- safety leak in input reports -> `REJECT_LSR_V2_PROMOTION_GATE_FAILED`.
