# PROMPT 29.4.4s-8 — LSR-v2 walk-forward / OOS / bootstrap validation suite

## Scope

Adds a diagnostic-only robustness validation suite for the locked LSR-v2 research profile:

`LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`

The validator consumes trade-level rows produced by `29.4.4s-7e` sample expansion:

`data/lsr_v2_sample_expansion_trades.jsonl`

It deduplicates repeated window-level representations of the same opportunity and then evaluates:

- temporal fold stability / walk-forward proxy;
- chronological out-of-sample holdout;
- bootstrap / Monte Carlo trade resampling;
- primary vs severe cost degradation;
- asset, timeframe and side stability;
- drawdown, top-level trade summary and sample sufficiency.

## Added files

```text
trading_bot/core/lsr_v2_robustness_validation.py
trading_bot/run_lsr_v2_robustness_validation.py
trading_bot/tests/test_lsr_v2_robustness_validation.py
trading_bot/docs/PROMPT_29_4_4S8_LSR_V2_ROBUSTNESS_VALIDATION_PATCH_REPORT.md
```

## Reports produced

```text
data/lsr_v2_robustness_validation_report.json
data/lsr_v2_walk_forward_report.json
data/lsr_v2_oos_report.json
data/lsr_v2_bootstrap_report.json
data/lsr_v2_walk_forward_trades.jsonl
```

## Decisions

```text
LSR_V2_ROBUSTNESS_VALIDATION_PASS
LSR_V2_READY_FOR_PROMOTION_GATE
KEEP_DIAGNOSTIC_LSR_V2_WALK_FORWARD_UNSTABLE
KEEP_DIAGNOSTIC_LSR_V2_OOS_FAILED
KEEP_DIAGNOSTIC_LSR_V2_BOOTSTRAP_FRAGILE
KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_FAILED
REJECT_LSR_V2_ROBUSTNESS_FAILED
KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_NO_TRADES
KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_ERROR
```

Even when the decision is `LSR_V2_READY_FOR_PROMOTION_GATE`, the patch keeps:

```text
promotion_ready=false
```

A separate promotion-gate patch is still required before any paper-supervised path.

## Safety invariants

The patch is diagnostic-only:

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

All report rows include zero order/position counters for this layer.

## Validation performed in sandbox

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_robustness_validation.py
```

Result:

```text
5 passed
```

Extended regression:

```text
python -m pytest -q \
  trading_bot/tests/test_lsr_v2_robustness_validation.py \
  trading_bot/tests/test_lsr_v2_sample_expansion.py \
  trading_bot/tests/test_lsr_v2_locked_profile.py \
  trading_bot/tests/test_lsr_v2_execution_ablation.py \
  trading_bot/tests/test_lsr_v2_backtest_matrix.py \
  trading_bot/tests/test_lsr_v2_trade_forensics.py \
  trading_bot/tests/test_liquidity_sweep_reversal_v2.py
```

Result:

```text
37 passed
```

Compilation:

```text
python -m compileall -q trading_bot
```

Result:

```text
compileall OK
```

No-data runner smoke test:

```text
python trading_bot/run_lsr_v2_robustness_validation.py --data-dir /mnt/data/s8_smoke
```

Result: `WARN / KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_NO_TRADES`, with zero order/position counters.

## Operator command after installation

Run after `29.4.4s-7e` has generated `data/lsr_v2_sample_expansion_trades.jsonl`:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_robustness_validation.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_robustness_validation.py --data-dir data
```

## Next step

If this patch returns `LSR_V2_READY_FOR_PROMOTION_GATE`, the next patch should be:

`29.4.4s-9 — LSR-v2 promotion gate / paper-supervised preflight`

If it returns any `KEEP_DIAGNOSTIC_*` or `REJECT_*` decision, LSR-v2 must remain research-only.
