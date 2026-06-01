# Prompt 29.4.4s-7d — LSR-v2 locked profile validation preflight / severe-cost failure drilldown

## Scope

This patch adds a diagnostic-only locked-profile validation layer for the best LSR-v2 execution variant found by `29.4.4s-7c`:

```text
LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24
retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24
```

The purpose is to stop comparing 72 ablation variants and instead inspect the single research profile that currently has the strongest conservative-cost edge. The patch measures conservative-vs-severe degradation trade by trade, window stability, exit distribution, side distribution, top-trade concentration, and break-even cost tolerance.

## Files added

```text
trading_bot/core/lsr_v2_locked_profile.py
trading_bot/run_lsr_v2_locked_profile.py
trading_bot/tests/test_lsr_v2_locked_profile.py
trading_bot/docs/PROMPT_29_4_4S7D_LSR_V2_LOCKED_PROFILE_PATCH_REPORT.md
PATCH_29_4_4S7D_MANIFEST.txt
```

## Reports produced

```text
data/lsr_v2_locked_profile_report.json
data/lsr_v2_locked_profile_trades.jsonl
data/lsr_v2_locked_profile_cost_drilldown.json
data/lsr_v2_locked_profile_window_stability.json
```

## Decisions

Possible main report decisions:

```text
LSR_V2_LOCKED_PROFILE_READY_FOR_WALK_FORWARD
KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_LOW_SAMPLE
KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_COST_SENSITIVE
KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_OUTLIER_DOMINATED
REJECT_LSR_V2_LOCKED_PROFILE
KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_NO_TRADES
KEEP_DIAGNOSTIC_NO_MARKET_DATA
KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA
KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_ERROR
```

## Safety invariants

This patch is audit-only and keeps all operational safety blocks intact:

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

## Validation performed in sandbox

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_locked_profile.py
# 5 passed

python -m pytest -q trading_bot/tests/test_lsr_v2_locked_profile.py trading_bot/tests/test_lsr_v2_execution_ablation.py trading_bot/tests/test_lsr_v2_backtest_matrix.py trading_bot/tests/test_lsr_v2_trade_forensics.py trading_bot/tests/test_liquidity_sweep_reversal_v2.py
# 27 passed

python -m compileall -q trading_bot
# OK
```

## Local commands

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_locked_profile.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_locked_profile.py --data-dir data --timeframe 5m
```

## Interpretation rule

Even if the locked profile returns positive conservative results, it must not be promoted to paper supervised from this patch. Promotion remains blocked until walk-forward, embargoed OOS, bootstrap/Monte Carlo, and a dedicated strategy promotion gate are implemented and passed.
