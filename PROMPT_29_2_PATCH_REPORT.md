# ProgettoTR — Prompt 29.2 Patch Report

## Scope

Implemented **29.2 — Paper performance monitor + drift detection** on top of the validated 29.1 paper lifecycle layer.

The patch is read-only with respect to strategy/execution decisions: it reads paper runtime files and writes monitoring artifacts.

## New artifact generator

Added:

```text
trading_bot/core/paper_performance.py
```

Runtime outputs:

```text
data/paper_performance_report.json
data/paper_drift_report.json
data/paper_dashboard.html
```

## Performance report

`paper_performance_report.json` includes:

- engine mode, symbols, timeframe, cost model;
- balance, equity, realized PnL, unrealized PnL;
- return percentage;
- current and observed max drawdown;
- equity curve from `CYCLE_COMPLETED` events;
- cycle counts and average cycle duration;
- asset scans, detected signals, rejected signals, no-signal ratio;
- submitted/filled/rejected order counts;
- open/closed positions, win rate and expectancy;
- exchange error rate;
- per-asset scan/order/error/expectancy table;
- per-archetype order/position/expectancy table when metadata is available;
- recent event tail for operator inspection.

The report supports zero-trade paper runs and will mark `NO_CLOSED_TRADES_YET` as a warning rather than a failure.

## Drift report

`paper_drift_report.json` compares observed paper behavior against the local backtest reference when available:

```text
data/execution_cost_stress_report.json
```

Fallback reference:

```text
data/multi_asset_robustness_report.json
```

Alert codes implemented:

```text
PAPER_DD_WARN
PAPER_EXPECTANCY_WARN
PAPER_SAMPLE_LOW
NO_SIGNAL_RATE_WARN
EXCHANGE_ERROR_RATE_WARN
ASSET_DRIFT_WARN
ARCHETYPE_DRIFT_WARN
```

Low-sample paper runs produce `PAPER_SAMPLE_LOW` as `INFO`; this does not fail the drift report.

## Local dashboard

`paper_dashboard.html` is a static auto-refreshing dashboard with:

- performance status;
- drift status;
- lifecycle status;
- mode/assets/timeframe/cost model;
- balance/equity/return/drawdown;
- open positions;
- no-signal ratio;
- orders/positions/error summary;
- asset scan table;
- drift alerts;
- recent events.

The page refreshes every 20 seconds and has no external dependencies.

## Paper engine integration

Modified:

```text
trading_bot/core/paper_engine.py
```

Changes:

- imports `write_performance_artifacts`;
- writes performance/drift/dashboard after every completed cycle;
- writes final performance/drift/dashboard during shutdown;
- enriches `CYCLE_COMPLETED` events with:
  - realized PnL;
  - unrealized PnL;
  - drawdown;
  - elapsed cycle seconds;
- adds report paths to `paper_status.json`;
- replaces the old verbose cycle line with compact operational CLI output:

```text
[HH:MM:SS] cycle=1 scanned=4 signals=0 orders=0 positions=0 equity=1000.00 dd=0.00% no_signal=4 errors=0 drift=PASS
```

## Validation performed in sandbox

Static validation:

```text
python -m py_compile trading_bot/core/paper_performance.py trading_bot/core/paper_engine.py
```

Artifact generation validation on included runtime files:

```text
write_performance_artifacts("data")
```

Generated successfully:

```text
data/paper_performance_report.json
data/paper_drift_report.json
data/paper_dashboard.html
```

Full paper runtime was not executed in sandbox because exchange dependencies such as `ccxt` are not installed there.

## Expected first-run interpretation

A clean one-cycle run with no trades should usually produce:

```text
paper_lifecycle_report.json: PASS
paper_performance_report.json: WARN
paper_drift_report.json: PASS
```

`paper_performance_report.json` is expected to be `WARN` until closed trades exist because `NO_CLOSED_TRADES_YET` is informationally important for monitoring.
