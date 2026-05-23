# Prompt 29.5.0c — Pattern-conditioned shadow/backtest review

## Scope

Diagnostic-only patch. It evaluates whether Prompt 29.5.0a scenario context and Prompt 29.5.0b candlestick-pattern context would have improved trade selection before any operational unlock.

## Safety guarantees

- Does not open paper orders.
- Does not change strategy thresholds.
- Does not enable testnet.
- Does not enable live execution.
- Does not convert pattern/scenario bias into operational entries.
- Keeps existing `BTC_ONLY_40_Q60` unlock gate unchanged.

## New module

```text
trading_bot/core/pattern_conditioned_shadow.py
```

The module writes:

```text
data/pattern_conditioned_shadow_report.json
```

It has two evidence sources:

1. Runtime review from `data/paper_events.jsonl`, joining:
   - `CRYPTO_SCENARIO_DIAGNOSTIC`
   - `CANDLESTICK_PATTERN_DIAGNOSTIC`
2. Optional historical shadow review from cached OHLCV parquet files, replaying scenario + candlestick detection causally and evaluating forward outcomes.

## New direct runner

```text
trading_bot/run_pattern_conditioned_shadow.py
```

Usage from project root:

```cmd
python trading_bot\run_pattern_conditioned_shadow.py
```

or from `trading_bot`:

```cmd
python run_pattern_conditioned_shadow.py
```

## Runtime integration

`PaperTradingEngine.write_performance_artifacts()` now generates the pattern-conditioned shadow report together with the other paper artifacts.

`paper_status.json` now includes:

```json
{
  "pattern_conditioned_shadow_enabled": true,
  "pattern_conditioned_shadow_report_path": "data\\pattern_conditioned_shadow_report.json",
  "pattern_conditioned_shadow": {
    "status": "...",
    "decision_status": "...",
    "runtime_aligned_candidates": 0,
    "historical_candidates": 0,
    "historical_expectancy_r": 0.0
  }
}
```

Telegram `/report` now includes pattern shadow status, historical candidate count and expectancy R.

## New config flags

```env
PATTERN_CONDITIONED_SHADOW_ENABLED=1
PATTERN_CONDITIONED_HISTORICAL_ENABLED=1
PATTERN_CONDITIONED_REPORT_PATH=data\pattern_conditioned_shadow_report.json
PATTERN_CONDITIONED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT
PATTERN_CONDITIONED_MAX_ROWS_PER_ASSET=5000
PATTERN_CONDITIONED_MIN_WARMUP_ROWS=450
PATTERN_CONDITIONED_EVAL_STRIDE=1
PATTERN_CONDITIONED_HORIZONS=3,6,12
PATTERN_CONDITIONED_STOP_LOSS_PCT=0.0035
PATTERN_CONDITIONED_TP1_PCT=0.0035
PATTERN_CONDITIONED_TP2_PCT=0.0070
PATTERN_CONDITIONED_MIN_OPERATIONAL_CANDIDATES=20
PATTERN_CONDITIONED_MIN_EXPECTANCY_R=0.05
```

## New CLI flag

```cmd
--no-pattern-conditioned-shadow
```

Disables the 29.5.0c report for the current paper run.

## Decision states

The report can return:

```text
SHADOW_EDGE_CANDIDATE
SHADOW_INCONCLUSIVE_OR_WEAK
RUNTIME_PATTERN_AVAILABLE_NEEDS_HISTORICAL_CONFIRMATION
NO_PATTERN_EDGE_EVIDENCE_YET
```

Only `SHADOW_EDGE_CANDIDATE` is a possible input for a later controlled profile refinement. It still does not enable operational trading by itself.

## Validation performed

- `py_compile` OK for:
  - `core/pattern_conditioned_shadow.py`
  - `core/paper_engine.py`
  - `core/paper_performance.py`
  - `run_paper_trading.py`
  - `run_pattern_conditioned_shadow.py`
- Runtime event-only smoke test OK.
- Historical parquet shadow is supported in the user's environment; sandbox validation could not read parquet because the sandbox lacks `pyarrow/fastparquet`.

## Recommended next command

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock

type data\pattern_conditioned_shadow_report.json
```

If CMD output is too long:

```cmd
notepad data\pattern_conditioned_shadow_report.json
```
