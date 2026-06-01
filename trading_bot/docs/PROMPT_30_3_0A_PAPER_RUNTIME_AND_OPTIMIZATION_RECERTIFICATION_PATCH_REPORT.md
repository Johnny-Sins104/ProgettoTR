# Prompt 30.3.0A - Paper runtime and optimization recertification

## Scope

This patch turns the paper/optimization checklist into an executable
recertification pass.

It fixes the runtime issues found while moving from static tests to actual
execution:

- bundled Windows SSL compatibility for `aiohttp`/`ccxt.async_support`;
- missing `plotly` runtime dependency for backtest visual reports;
- paper `--once` watchdog reliability after `CYCLE_COMPLETED`;
- candlestick pattern strictness regressions found by full pytest.

## Validation

- `python tools\run_checks.py --require-deps` -> PASS: 26 smoke tests passed, no missing dependencies.
- `python -m pytest -q` -> PASS: 1006 passed, 2 warnings.
- `python trading_bot\run_paper_trading.py --mode paper --once --symbols BTC/USDT --timeframe 5m --balance 1000 --poll-seconds 1 --no-telegram-proactive` -> completed a paper cycle and exited through the watchdog.
- Offline `run_custom_backtest.py --fast --risk-profile DYNAMIC --cost-model conservative --no-download-cache --no-charts --quiet-wf` -> PASS.
- `run_lsr_v2_backtest_matrix.py` -> PASS diagnostic.
- `run_lsr_v2_robustness_validation.py` -> PASS diagnostic.
- `run_edge_strategy_discovery.py` -> WARN diagnostic.

## Paper smoke result

The paper engine starts, restores state, records `ENGINE_STARTED`,
`CYCLE_STARTED`, `SYMBOL_ERROR`, `EXCHANGE_CLIENT_CLOSED`, and
`CYCLE_COMPLETED`, then exits cleanly through:

```text
reason=cycle_completed_watchdog_hard_exit
```

The cycle itself cannot scan live candles from this environment because the
exchange endpoint returns `ExchangeNotAvailable`.

Tested exchange fetches:

- `binanceusdm` -> `ExchangeNotAvailable`
- `binance` -> `ExchangeNotAvailable`
- `okx` -> `ExchangeNotAvailable`
- `bybit` -> `ExchangeNotAvailable`

## Optimization status

The optimization stack exists and runs, but current recertification does not
approve autonomous paper order submission.

Backtest DYNAMIC conservative:

- final balance: `93.86`
- net PnL: `-6.14%`
- closed trades: `10`
- paper readiness: `NOT_READY`

LSR-v2 matrix:

- status: `PASS`
- decision: `KEEP_DIAGNOSTIC_LSR_V2_NOT_READY`
- closed trades: `22`
- weighted avg R post cost: `0.26886306`
- promotion ready: `false`
- blockers: sample size, top-trade concentration, severe-cost survival.

LSR-v2 robustness:

- status: `PASS`
- decision: `KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_FAILED`
- promotion ready: `false`
- blockers: cost degradation and max drawdown.

Edge strategy discovery:

- status: `WARN`
- valid strategies: `0`
- watchlist: `LIQUIDITY_SWEEP_REVERSAL`
- hard-block recommendation: `RANGING_MEAN_REVERSION`

## Operational conclusion

The codebase is test-clean and the paper runner can start and exit cleanly.
Continuous paper operation is blocked by live market-data access from this
runtime, and strategy promotion remains diagnostic until the optimization
reports pass their own readiness gates.
