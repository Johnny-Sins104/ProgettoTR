# Prompt 29.4.3 — Conservative threshold simulation / shadow unlock analysis

## Scope

Adds a non-operative shadow simulation layer for paper signal-density analysis.
The patch evaluates historical and exact paper diagnostics under alternative
threshold profiles without changing strategy gates, order flow, position state,
risk sizing, broker adapters, Telegram control, testnet, or live execution.

## Files changed

- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/core/paper_shadow_simulation.py` *(new)*
- `.env.example`
- `docs/patch_reports/PROMPT_29_4_3_PATCH_REPORT.md`

## New artifact

- `data/paper_shadow_unlock_report.json`

## New configuration

```env
PAPER_SHADOW_SIMULATION_ENABLED=1
PAPER_SHADOW_INCLUDE_INFERRED=1
PAPER_SHADOW_MAX_HOLD_CYCLES=12
PAPER_SHADOW_STOP_LOSS_PCT=0.0035
PAPER_SHADOW_TP1_PCT=0.0035
PAPER_SHADOW_TP2_PCT=0.0070
```

## Shadow profiles

The report currently evaluates:

- `CURRENT_GATES`
- `CONSERVATIVE_45_Q60`
- `CONSERVATIVE_40_Q60`
- `CONSERVATIVE_35_Q60`
- `BTC_ONLY_40_Q60`
- `BTC_ONLY_35_Q60`

All profiles are diagnostic-only.

## Simulation model

The model uses only persisted paper runtime artifacts:

- candidate diagnostics from `SIGNAL_DIAGNOSTIC`
- inferred legacy diagnostics from old `NO_SIGNAL` events
- entry/forward price proxy from `ASSET_SCANNED.last_price`

The simulation is close/mark-only. It does not model intrabar path, slippage,
partial fills, book liquidity, order queueing, exchange rejections, or live/testnet
execution.

## Safety guarantees

- `PAPER_ENTRY_UNLOCK_ENABLED` remains false by default.
- No strategy thresholds are changed.
- No paper orders are forced.
- No broker positions are created by the shadow layer.
- No live/testnet path is enabled.
- `ExchangeBrokerAdapter` remains a blocked design stub.

## Validation performed

- `py_compile` passed for changed files.
- Smoke test generated `data/paper_shadow_unlock_report.json` from the supplied
  runtime event log.
- `write_performance_artifacts()` included the shadow report in the paper
  performance payload and dashboard.

## Observed smoke-test summary on supplied runtime data

```text
shadow_rows_total: 197
CURRENT_GATES: 0 simulated rows
CONSERVATIVE_45_Q60: 0 simulated rows
CONSERVATIVE_40_Q60: 27 simulated rows, expectancy_r ≈ +0.1685
CONSERVATIVE_35_Q60: 89 simulated rows, expectancy_r ≈ -0.0913
BTC_ONLY_40_Q60: 21 simulated rows, expectancy_r ≈ +0.1676
BTC_ONLY_35_Q60: 60 simulated rows, expectancy_r ≈ -0.0583
```

Interpretation: the 40/Q60 profiles are worth further observation, but the sample
is still too small and close-only to justify operational unlock. The 35/Q60
profiles are too loose in the current sample.

## Operator validation commands

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once

type data\paper_shadow_unlock_report.json
type data\paper_performance_report.json
type data\paper_status.json
```

Optional disable switch:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --no-shadow-simulation
```
