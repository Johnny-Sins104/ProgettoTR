# ProgettoTR

Paper-first trading bot laboratory. Live/testnet real-money execution is blocked
by `trading_bot/avvia_bot_live.py` until the paper path is proven and promoted.

## Clean Bot Lab

Default paper profile is `active`: more signals than `conservative`, still
paper-only. Use `--profile conservative` for the slower, stricter profile, or
`--profile aggressive` for higher-frequency paper observation with higher
drawdown risk.

Show available read-only tools:

```powershell
python trading_bot\avvia_bot_live.py --paper-tools
```

Run the current clean trend candidate backtest:

```powershell
python trading_bot\avvia_bot_live.py --clean-backtest --symbol XRP/USDT --profile active --max-rows 150000
```

Run multi-asset optimization diagnostics:

```powershell
python trading_bot\avvia_bot_live.py --clean-optimize --symbols all --max-rows 150000
```

Run frequency audit:

```powershell
python trading_bot\avvia_bot_live.py --clean-frequency-audit
```

Download public 1m XRP data for scalping research:

```powershell
python trading_bot\avvia_bot_live.py --clean-download-1m --symbol XRP/USDT --days 90
```

Run 1m scalping audit with realistic costs:

```powershell
python trading_bot\avvia_bot_live.py --clean-scalping-1m-audit --symbol XRP/USDT --max-rows 150000
```

Only promote a 1m scalping profile after the audit reports `accepted_count > 0`
with realistic costs. A zero-cost diagnostic is useful for research, but is not
tradable.

Check clean paper health, signals, skips, trades, and Telegram env:

```powershell
python trading_bot\avvia_bot_live.py --clean-monitor --tail 2000
```

Send the monitor report to Telegram:

```powershell
python trading_bot\avvia_bot_live.py --clean-monitor --tail 2000 --telegram
```

Build the safe cleanup map:

```powershell
python trading_bot\avvia_bot_live.py --clean-cleanup-plan
```

Run one clean paper cycle without touching the legacy paper state:

```powershell
python trading_bot\avvia_bot_live.py --clean-paper --symbol XRP/USDT --profile active --market-data-mode cache --once
```

Run the clean paper runner on live public market data:

```powershell
python trading_bot\avvia_bot_live.py --clean-paper --symbol XRP/USDT --profile active --market-data-mode live --poll-seconds 60
```

Test Telegram before starting the runner:

```powershell
python trading_bot\avvia_bot_live.py --clean-paper --telegram-test
```

Send cycle summaries to Telegram during a run:

```powershell
python trading_bot\avvia_bot_live.py --clean-paper --symbol XRP/USDT --profile active --market-data-mode live --poll-seconds 60 --telegram --telegram-every-cycle
```

Start the existing supervised paper-live runner:

```powershell
.\avvia_bot_live.bat
```

## Strategy Selector Dashboard Preflight

Patch `29.4.4u-69` adds a read-only strategy selector scaffold for:
`ema_vwap`, `bb`, `macd`, `ichimoku`, and disabled/read-only `auto`.

Validate it with:

```powershell
python -m compileall trading_bot
python -m pytest tests/test_strategy_selector_dashboard_preflight.py -q
python trading_bot\run_strategy_selector_dashboard_preflight.py
```

Open the local read-only selector dashboard:

```powershell
python trading_bot\run_strategy_selector_dashboard_server.py
```

Then open:

```text
http://127.0.0.1:8787/dashboard
```

## Strategy Selector Shadow Signal Execution

Run the selected-strategy shadow signal executor:

```powershell
python trading_bot\run_strategy_selector_shadow_signal_execution.py
```

Validate the shadow patch:

```powershell
python -m compileall trading_bot
python -m pytest tests/test_strategy_selector_shadow_signal_execution.py -q
python trading_bot\run_strategy_selector_shadow_signal_execution.py
```

The executor writes:

```text
data/strategy_shadow_signal_report.json
```

It evaluates only the selected `active_strategy` and keeps `would_trade=false`.

## Selected Strategy Shadow Journal

Append the selected strategy shadow signal to the diagnostic journal:

```powershell
python trading_bot\run_selected_strategy_shadow_signal_journal.py
```

Validate the journal patch:

```powershell
python -m compileall trading_bot
python -m pytest tests/test_selected_strategy_shadow_signal_journal.py -q
python trading_bot\run_selected_strategy_shadow_signal_journal.py
```

The runner writes:

```text
data/selected_strategy_shadow_signal_journal.jsonl
data/selected_strategy_shadow_signal_report.json
```
