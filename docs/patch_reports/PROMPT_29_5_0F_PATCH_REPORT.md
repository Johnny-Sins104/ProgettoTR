# Prompt 29.5.0f — Calibrated scenario-pattern-structure shadow review

Status: diagnostic-only patch.

## Objective

Add a conservative shadow-review layer that combines:

- 29.5.0a crypto intraday scenarios;
- 29.5.0b candlestick pattern diagnostics;
- 29.5.0d scenario-pattern calibration;
- 29.5.0e liquidity / supply-demand / structure map.

The patch checks whether the non-operational profile candidate
`BTC_BUY_REJECTION_PATTERN_CONFIRMED` improves when filtered by structure context
and hard structural confirmation.

## New files

```text
trading_bot/core/calibrated_structure_shadow.py
trading_bot/run_calibrated_structure_shadow.py
trading_bot/test_calibrated_structure_shadow.py
docs/patch_reports/PROMPT_29_5_0F_PATCH_REPORT.md
```

## Updated files

```text
trading_bot/config.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/run_paper_trading.py
```

## Output

```text
data/calibrated_structure_shadow_report.json
```

## Report comparisons

The report builds and ranks these variants:

```text
baseline_scenario_pattern_structured_sample
clean_pattern_range_filter
structure_context_all_assets
structure_confirmed_all_assets
btc_focus_clean
btc_focus_score_60_clean
btc_focus_score_60_structure_context
btc_focus_score_60_structure_confirmed
btc_focus_score_65_clean
btc_focus_score_65_structure_context
btc_focus_score_65_structure_confirmed
btc_focus_score_70_clean
btc_focus_score_70_structure_context
btc_focus_score_70_structure_confirmed
```

Each variant includes:

```text
candidates
expectancy_r
win_rate_pct
loss_rate_pct
TP1 / TP2 / SL / TIME_EXIT rates
pattern_score distribution
map_score distribution
range_pos_400 distribution
structure_bias counts
price_location counts
confirmation_summary counts
passes_candidate_gate
```

## Gate logic

A variant can become a **non-operational structure-filter candidate** only if it
passes all shadow gates:

```text
candidates >= CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES
expectancy_r >= CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R
win_rate_pct >= CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT
loss_rate_pct <= CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT
time_exit_rate_pct <= CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT
```

Default gates:

```text
min candidates = 50
min expectancy = +0.10 R
min win rate = 52%
max loss rate = 45%
max time exit rate = 60%
```

## Safety invariants

This patch does not:

```text
open orders
enable paper unlock
enable testnet
enable live execution
change risk
change strategy thresholds
expand assets operationally
```

All outputs are diagnostic and review-only.

## Local validation commands

```cmd
python trading_bot\test_calibrated_structure_shadow.py
python trading_bot\test_market_structure_map.py
python trading_bot\test_scenario_pattern_calibration.py
python trading_bot\run_calibrated_structure_shadow.py
```

Expected runner output in a full local environment with parquet support:

```json
{
  "status": "PASS" or "WARN",
  "decision": "STRUCTURE_FILTER_CANDIDATE" or "KEEP_DIAGNOSTIC",
  "candidate_profile": "BTC_BUY_REJECTION_PATTERN_CONFIRMED",
  "report": "data\\calibrated_structure_shadow_report.json"
}
```

`STRUCTURE_FILTER_CANDIDATE` is still non-operational. It only means a candidate
profile can be reviewed later by `29.4.4c — Paper unlock profile refinement`.
