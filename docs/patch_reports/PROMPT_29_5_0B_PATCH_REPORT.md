# Prompt 29.5.0b — Candlestick pattern feature engine + scenario integration

## Scope

Adds a diagnostic-only candlestick feature layer that detects explicit candle patterns and combines them with the Prompt 29.5.0a crypto intraday scenario engine.

The patch is designed to address the output of Prompt 29.5.0a, where the bot identified scenarios such as `NEAR_SUPPORT` but still had `directional_bias=HOLD` because it lacked richer candle/retest/reclaim confirmation.

## Safety

This patch does not:

- open orders
- change thresholds
- enable live execution
- enable testnet
- increase risk
- convert pattern bias into operational unlock

All new logic is diagnostic-only.

## New module

```text
trading_bot/core/candlestick_patterns.py
```

Main functions:

```text
detect_candlestick_patterns()
build_candlestick_pattern_diagnostic()
write_candlestick_pattern_report()
```

## New event

```text
CANDLESTICK_PATTERN_DIAGNOSTIC
```

Each event includes:

- detected patterns
- bullish/bearish/neutral pattern buckets
- pattern bias: `BUY`, `SELL`, or `HOLD`
- pattern score
- integration with scenario context
- pattern alignment versus engine/scenario
- confirmations and missing confirmations
- candle metrics: body ratio, wick ratios, volume ratio

## Patterns detected

Single-candle:

```text
doji
hammer
shooting_star
bullish_pin_bar
bearish_pin_bar
```

Two-candle:

```text
bullish_engulfing
bearish_engulfing
inside_bar
outside_bar
bullish_outside_bar
bearish_outside_bar
```

Three-candle:

```text
morning_star
evening_star
bullish_three_bar_reversal
bearish_three_bar_reversal
```

Structure/candle combinations:

```text
fake_breakdown_reclaim
fake_breakout_reclaim
breakout_retest_hold
breakdown_retest_reject
```

## New report

```text
data/candlestick_pattern_report.json
```

The report contains:

- total pattern events
- BTC pattern events
- pattern counts
- pattern bias distribution
- pattern/scenario integration
- pattern alignment
- per-asset summaries
- BTC focus summary
- decision block with recommended next step

## Config flags

```env
PAPER_CANDLESTICK_PATTERNS_ENABLED=1
PAPER_CANDLESTICK_PATTERN_REPORT_PATH=data/candlestick_pattern_report.json
CANDLE_PATTERN_MIN_BODY_RATIO=0.25
CANDLE_PATTERN_STRONG_BODY_RATIO=0.55
CANDLE_PATTERN_DOJI_BODY_RATIO=0.12
CANDLE_PATTERN_WICK_RATIO=0.45
CANDLE_PATTERN_PIN_WICK_TO_BODY=2.0
CANDLE_PATTERN_INSIDE_TOLERANCE_PCT=0.0002
CANDLE_PATTERN_OUTSIDE_TOLERANCE_PCT=0.0002
CANDLE_PATTERN_RECLAIM_BUFFER_PCT=0.0003
CANDLE_PATTERN_RETEST_TOLERANCE_PCT=0.0015
CANDLE_PATTERN_VOLUME_RATIO_THRESHOLD=1.10
```

Runtime disable flag:

```cmd
--no-candlestick-patterns
```

## Integration points

Updated files:

```text
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/config.py
trading_bot/run_paper_trading.py
```

The paper engine now emits `CANDLESTICK_PATTERN_DIAGNOSTIC` after the scenario diagnostic and before unlock evaluation. `NO_SIGNAL`, `SIGNAL_DETECTED`, and order metadata receive pattern context fields where available.

## Expected behavior

Run:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Then inspect:

```cmd
type data\candlestick_pattern_report.json
```

or:

```cmd
notepad data\candlestick_pattern_report.json
```

## Validation

Completed in sandbox:

```text
py_compile OK
synthetic pattern detection smoke test OK
```

Runtime exchange execution was not performed in sandbox.

## Next likely patch

If the report finds directional BTC candle confirmations aligned with the scenario context:

```text
29.5.0c — Pattern-conditioned shadow review
```

This would remain shadow-only and would test whether pattern-confirmed scenarios would have improved expectancy before any operational unlock is considered.
