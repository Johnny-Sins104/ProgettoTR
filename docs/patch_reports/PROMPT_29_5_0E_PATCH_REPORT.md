# Prompt 29.5.0e — Liquidity + supply/demand + structure break engine

Date: 2026-05-23
Status: implemented as diagnostic-only layer

## Scope

Patch 29.5.0e adds an explicit market-structure map to ProgettoTR.  The patch is designed to answer:

- where price is located relative to demand/supply;
- which liquidity pools are nearby;
- whether equal highs/equal lows exist;
- whether structure is bullish, bearish or ranging;
- whether BOS, CHOCH or MSS is present;
- which confirmation is still missing.

## New files

```text
trading_bot/core/market_structure_map.py
trading_bot/run_market_structure_map.py
trading_bot/test_market_structure_map.py
docs/patch_reports/PROMPT_29_5_0E_PATCH_REPORT.md
```

## Updated files

```text
trading_bot/config.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/run_paper_trading.py
```

## New report

```text
data/market_structure_map_report.json
```

The report contains:

```text
runtime MARKET_STRUCTURE_MAP_DIAGNOSTIC rows
historical map snapshots by asset
equal_highs / equal_lows
liquidity_above_highs / liquidity_below_lows
demand_zone_low / demand_zone_high
supply_zone_low / supply_zone_high
bos_bullish / bos_bearish
choch_bullish / choch_bearish
mss_bullish / mss_bearish
swing_sequence
last_HH / last_HL / last_LH / last_LL
breakout_retest_confirmed
breakdown_retest_confirmed
failed_retest
confirmation_close
missing_confirmation
confirmation_summary
```

## Safety guarantees

The patch is diagnostic-only:

```text
opens_orders = false
enables_live_or_testnet = false
changes_thresholds = false
operational_unlock_allowed = false
paper_unlock_unchanged = true
```

It does not enable testnet, live execution, paper unlock, higher risk, or multi-asset operational expansion.

## Runtime integration

When the paper engine evaluates a symbol, it now emits:

```text
MARKET_STRUCTURE_MAP_DIAGNOSTIC
```

The event is attached to no-signal/signal metadata only for auditability. It does not affect trade decisions.

## Commands

Run the unit test:

```cmd
python trading_bot\test_market_structure_map.py
```

Generate the report:

```cmd
python trading_bot\run_market_structure_map.py
```

Expected output file:

```text
data\market_structure_map_report.json
```

## Expected decision

The normal decision after this patch is:

```text
STRUCTURE_MAP_READY_DIAGNOSTIC
```

or, if parquet engines/caches are unavailable:

```text
STRUCTURE_MAP_PARTIAL_WARN
```

In both cases:

```text
operational_unlock_allowed = false
```

## Next patch

The next patch remains:

```text
29.5.0f — Calibrated scenario-pattern-structure shadow review
```

That patch should combine the calibrated scenario/pattern profile from 29.5.0d with the structure map from 29.5.0e and test whether BTC BUY_REJECTION candidates improve after structure confirmation.


## Hotfix 29.5.0e-1

The historical CLI runner now uses bounded snapshot sampling and a fixed evaluation window for each asset. This prevents long pandas replay loops when local parquet caches are available. The change is diagnostic-only and does not change thresholds, risk, paper unlock, testnet, live execution, or order flow.

New optional environment knobs:

```text
MARKET_STRUCTURE_MAP_EVAL_STRIDE=25
MARKET_STRUCTURE_MAP_MAX_SNAPSHOTS_PER_ASSET=160
MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS=900
```
