# Prompt 29.4.4s-6b — LSR-v2 timeframe/input strictness + candidate quality report

## Scope

Diagnostic-only hardening patch for `29.4.4s-6 — LSR-v2 audit-only candidate detector`.

The previous validation showed that `--timeframe 5m` could load `data\\btc_15m_50k_cache.parquet`. This patch prevents silent timeframe drift and adds candidate-quality telemetry for the next cost-stress/backtest matrix.

## Safety invariant

This patch does not submit orders, open positions, route to a broker, call an exchange broker, enable live, enable testnet, change risk, lower thresholds, or promote any strategy. `promotion_ready` remains `false`.

## Files changed / added

- `trading_bot/core/liquidity_sweep_reversal_v2.py`
- `trading_bot/run_lsr_v2_candidate_audit.py`
- `trading_bot/tests/test_liquidity_sweep_reversal_v2.py`
- `trading_bot/docs/PROMPT_29_4_4S6B_LSR_V2_TIMEFRAME_QUALITY_PATCH_REPORT.md`

## Main changes

### Strict timeframe matching

New settings:

- `strict_timeframe=True` by default
- `allow_timeframe_fallback=False` by default

The runner now records:

- `requested_timeframe`
- `detected_timeframe`
- `timeframe_match`
- `strict_timeframe`
- `allow_timeframe_fallback`
- `timeframe_mismatch_paths`

When `--timeframe 5m` only finds `15m` market data, the runner returns:

```json
{
  "status": "WARN",
  "decision": "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
}
```

A mismatch can be loaded only with explicit operator intent:

```powershell
python trading_bot\run_lsr_v2_candidate_audit.py --data-dir data --timeframe 5m --allow-timeframe-fallback
```

### Candidate quality report

Each LSR-v2 event now includes a diagnostic `quality` object:

- `grade`: `A`, `B`, or `C`
- `score`
- `reasons`
- `atr_proxy`
- `sweep_depth_abs`
- `sweep_depth_atr`
- `reclaim_strength_abs`
- `reclaim_strength_atr`
- `retest_distance_abs`
- `retest_distance_atr`

The report summary now includes:

- `candidate_density_pct`
- `ready_density_pct`
- `retest_to_ready_ratio`
- `candidate_to_ready_ratio`
- `quality_A`, `quality_B`, `quality_C`
- `ready_quality_A`, `ready_quality_B`, `ready_quality_C`
- `median_rr`, `min_rr`, `max_rr`, `ready_median_rr`
- `avg_sweep_depth_atr`
- `avg_reclaim_strength`
- `avg_retest_distance_atr`
- `long_count`, `short_count`

## Validation commands

```powershell
python -m pytest -q trading_bot\tests\test_liquidity_sweep_reversal_v2.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_candidate_audit.py --data-dir data --timeframe 5m
```

## Expected post-patch behavior

If no matching 5m data exists but 15m data exists:

```json
{
  "status": "WARN",
  "decision": "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA",
  "requested_timeframe": "5m",
  "timeframe_match": false
}
```

If matching 5m data exists:

```json
{
  "status": "PASS",
  "decision": "LSR_V2_CANDIDATE_AUDIT_READY_DIAGNOSTIC",
  "requested_timeframe": "5m",
  "detected_timeframe": "5m",
  "timeframe_match": true,
  "promotion_ready": false
}
```

## Next step

After local validation, proceed to:

`29.4.4s-7 — LSR-v2 backtest matrix / cost stress grid`
