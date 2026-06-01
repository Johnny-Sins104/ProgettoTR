# PROMPT 29.4.4s-7e — LSR-v2 sample expansion / data horizon robustness audit

## Scope

This patch adds a diagnostic-only sample expansion layer for the locked LSR-v2 research profile:

`LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`

Locked variant:

`retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24`

The audit scans available market-data cache files for requested assets/timeframes, reruns the locked profile across expanded windows, and reports whether the current blocker is likely low sample size, cost sensitivity, asset specificity, timeframe specificity, or insufficient sample.

## Added files

- `trading_bot/core/lsr_v2_sample_expansion.py`
- `trading_bot/run_lsr_v2_sample_expansion.py`
- `trading_bot/tests/test_lsr_v2_sample_expansion.py`
- `trading_bot/docs/PROMPT_29_4_4S7E_LSR_V2_SAMPLE_EXPANSION_PATCH_REPORT.md`

## Output artifacts

- `data/lsr_v2_sample_expansion_report.json`
- `data/lsr_v2_sample_expansion_by_asset.json`
- `data/lsr_v2_sample_expansion_by_timeframe.json`
- `data/lsr_v2_sample_expansion_trades.jsonl`

## Decisions

Possible top-level decisions:

- `LSR_V2_SAMPLE_EXPANSION_READY_FOR_WALK_FORWARD`
- `KEEP_DIAGNOSTIC_LSR_V2_LOW_SAMPLE`
- `KEEP_DIAGNOSTIC_LSR_V2_ASSET_SPECIFIC`
- `KEEP_DIAGNOSTIC_LSR_V2_TIMEFRAME_SPECIFIC`
- `REJECT_LSR_V2_INSUFFICIENT_SAMPLE`
- `KEEP_DIAGNOSTIC_NO_MARKET_DATA`
- `KEEP_DIAGNOSTIC_LSR_V2_SAMPLE_EXPANSION_ERROR`

## Safety properties

This patch is strictly diagnostic-only:

- no live trading
- no testnet trading
- no exchange broker
- no broker call
- no order submission
- no position opening
- no paper-state mutation
- no runtime routing
- no threshold lowering
- `promotion_ready=false`

## Validation performed in sandbox

```bash
python -m pytest -q trading_bot/tests/test_lsr_v2_sample_expansion.py
# 5 passed

python -m pytest -q \
  trading_bot/tests/test_lsr_v2_sample_expansion.py \
  trading_bot/tests/test_lsr_v2_locked_profile.py \
  trading_bot/tests/test_lsr_v2_execution_ablation.py \
  trading_bot/tests/test_lsr_v2_backtest_matrix.py \
  trading_bot/tests/test_lsr_v2_trade_forensics.py \
  trading_bot/tests/test_liquidity_sweep_reversal_v2.py
# 32 passed

python -m compileall -q trading_bot
# OK
```

Synthetic CLI validation:

```bash
python trading_bot/run_lsr_v2_sample_expansion.py \
  --data-dir data \
  --symbols BTC/USDT \
  --timeframes 5m \
  --windows 90 \
  --cost-models conservative,severe \
  --min-closed-trades 1 \
  --min-positive-windows 1 \
  --min-severe-positive-windows 0
```

Returned diagnostic PASS with no orders and no positions.

## Local command

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_sample_expansion.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_sample_expansion.py --data-dir data --symbols BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT --timeframes 5m,15m
```

## Interpretation guideline

If the report remains low-sample with only BTC 5m/15m data available, do not promote LSR-v2. If closed trades rise above the minimum and the locked profile remains positive across expanded horizons, proceed only to walk-forward/OOS/bootstrap validation. This patch does not authorize paper supervised execution.
