# Prompt 29.5.0a — Crypto intraday scenario engine

## Scope

Adds a diagnostic-only crypto intraday scenario layer for the paper runtime. The layer converts existing OHLCV, support/resistance, range-position, volume, candle-shape and regime features into explicit operational scenarios.

This patch is designed to address the Prompt 29.4.4a diagnosis where BTC unlock candidates were rejected mainly by `no_intended_side` and `TECH_SCORE_LOW` rather than by a safely recoverable unlock threshold.

## Safety constraints

- Does not open paper orders.
- Does not modify strategy verdicts.
- Does not relax AI, setup-quality, technical-score, range-position or risk thresholds.
- Does not enable testnet or live execution.
- Does not use screenshots, OCR or chart images.
- Uses exchange OHLCV/indicator data already available to the runtime.

## New module

```text
trading_bot/core/crypto_intraday_scenario.py
```

Primary functions:

```text
evaluate_crypto_intraday_scenario()
build_crypto_scenario_diagnostic()
build_crypto_scenario_report()
write_crypto_scenario_report()
```

## New event

```text
CRYPTO_SCENARIO_DIAGNOSTIC
```

One event is emitted per scanned asset when scenario diagnostics are enabled.

The event includes:

```text
scenario
directional_bias
current_zone
confidence_score
allowed_setups
blocked_setups
recommendation
scenario_alignment
levels
candle
context
```

## Scenarios

Initial scenario taxonomy:

```text
MID_RANGE_NO_TRADE
NEAR_SUPPORT
NEAR_RESISTANCE
BUY_BREAKOUT_CANDIDATE
SELL_BREAKDOWN_CANDIDATE
BUY_REJECTION_CANDIDATE
SELL_REJECTION_CANDIDATE
TREND_CONTEXT_WAIT_PULLBACK
WAIT_FOR_CONFIRMATION
```

## New report

```text
data/crypto_intraday_scenario_report.json
```

The report summarizes:

```text
scenario event count
BTC scenario events
scenario distribution
directional bias distribution
scenario/engine alignment
by-asset scenario table
recent scenarios
automatic recommendation
```

## Runtime integration

Updated files:

```text
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/config.py
trading_bot/run_paper_trading.py
```

Runtime integrations:

```text
- emits CRYPTO_SCENARIO_DIAGNOSTIC after SIGNAL_DIAGNOSTIC
- adds scenario context to NO_SIGNAL events
- adds scenario context to SIGNAL_DETECTED metadata
- writes crypto_intraday_scenario_report.json during performance artifact generation
- exposes scenario status in paper_status.json
- exposes scenario status in /report
- adds scenario section to paper_dashboard.html
```

## Config

New environment variables:

```env
PAPER_CRYPTO_SCENARIO_ENABLED=1
PAPER_CRYPTO_SCENARIO_REPORT_PATH=data/crypto_intraday_scenario_report.json
CRYPTO_SCENARIO_SR_PROXIMITY_PCT=0.0035
CRYPTO_SCENARIO_BREAKOUT_BUFFER_PCT=0.0005
CRYPTO_SCENARIO_MIN_BODY_RATIO=0.35
CRYPTO_SCENARIO_REJECTION_WICK_RATIO=0.45
CRYPTO_SCENARIO_VOLUME_RATIO_THRESHOLD=1.10
CRYPTO_SCENARIO_NO_TRADE_LOW=0.40
CRYPTO_SCENARIO_NO_TRADE_HIGH=0.60
CRYPTO_SCENARIO_RANGE_EXTREME_LOW=0.25
CRYPTO_SCENARIO_RANGE_EXTREME_HIGH=0.75
```

CLI override:

```cmd
--no-crypto-scenario
```

## Validation

Performed in sandbox:

```text
py_compile OK:
- config.py
- run_paper_trading.py
- core/paper_engine.py
- core/paper_performance.py
- core/crypto_intraday_scenario.py

Synthetic scenario smoke test OK:
- BUY_BREAKOUT_CANDIDATE detected
- directional_bias BUY
- alignment SCENARIO_HAS_DIRECTION_BUT_ENGINE_HOLD

Report generation OK on existing data:
- status WARN when no CRYPTO_SCENARIO_DIAGNOSTIC events exist yet
- write_performance_artifacts includes crypto_scenario payload
```

Full exchange runtime was not executed in the sandbox environment.

## Expected operator workflow

After applying the patch:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Then inspect:

```cmd
type data\crypto_intraday_scenario_report.json
```

If CMD output is too long:

```cmd
notepad data\crypto_intraday_scenario_report.json
```

## Decision rule after first real run

If the report shows `SCENARIO_HAS_DIRECTION_BUT_ENGINE_HOLD`, the next logical step is:

```text
29.5.0b — Candlestick pattern feature engine + scenario integration
```

If `MID_RANGE_NO_TRADE` dominates, do not force entries.

If `NEAR_SUPPORT` / `NEAR_RESISTANCE` appears often without accepted signals, use the scenario report to guide 29.4.4c profile refinement, still without live/testnet.
