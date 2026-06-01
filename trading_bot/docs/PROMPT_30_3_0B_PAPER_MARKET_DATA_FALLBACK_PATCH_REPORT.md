# Prompt 30.3.0B - Paper market-data fallback and replay mode

## Scope

This patch removes the current operational blocker for controlled paper-mode
drills in environments where exchange HTTPS endpoints are unavailable.

The default behavior remains unchanged:

```text
--market-data-mode live
```

New paper-only modes:

- `auto`: try live exchange data first; if it fails, emit a fallback event and use local replay cache.
- `cache`: use the latest local cached OHLCV window.
- `replay`: advance through local cached OHLCV candles one step per paper cycle.

The implementation is read-only with respect to market data. It does not enable
live/testnet brokers, bypass risk gates, submit real orders, or promote any
strategy.

## Runtime usage

Controlled replay paper smoke:

```powershell
python trading_bot\run_paper_trading.py --mode paper --once --symbols BTC/USDT --timeframe 5m --balance 1000 --poll-seconds 1 --market-data-mode replay --market-data-cache-dir data --no-telegram-proactive
```

Auto fallback smoke:

```powershell
python trading_bot\run_paper_trading.py --mode paper --once --symbols BTC/USDT --timeframe 5m --balance 1000 --poll-seconds 1 --market-data-mode auto --market-data-cache-dir data --no-telegram-proactive
```

For continuous supervised replay, omit `--once` and keep a conservative
poll interval:

```powershell
python trading_bot\run_paper_trading.py --mode paper --symbols BTC/USDT --timeframe 5m --balance 1000 --poll-seconds 60 --market-data-mode replay --market-data-cache-dir data --no-telegram-proactive
```

## Validation

- `py_compile` on changed runtime/test files: PASS.
- `trading_bot\test_runtime_risk_io_hardening.py`: PASS.
- Replay paper `--once`: PASS, 500 local candles loaded, cycle completed.
- Auto fallback paper `--once`: PASS, `ExchangeNotAvailable` recorded, local replay cache used, cycle completed with `scanned=1`, `errors=0`.
- `tools\run_checks.py --require-deps`: PASS, 29 smoke tests passed.
- `python -m pytest`: PASS, 1009 passed, 2 warnings.

## Events added

- `MARKET_DATA_LIVE_USED`
- `MARKET_DATA_LIVE_FAILED_FALLBACK`
- `MARKET_DATA_CACHE_USED`

These events are diagnostic only and are written to `paper_events.jsonl`.

## Operational conclusion

Paper mode can now run in this local environment even while live exchange data
is blocked. True live-data paper remains dependent on exchange/network access,
and optimization readiness is still not approved for autonomous paper order
submission.
