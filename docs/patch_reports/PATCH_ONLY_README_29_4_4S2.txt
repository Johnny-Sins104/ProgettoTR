Prompt 29.4.4s-2 — Edge strategy discovery / archetype performance hardening

Patch-only contents:
- trading_bot/core/edge_strategy_discovery.py
- trading_bot/run_edge_strategy_discovery.py
- trading_bot/test_edge_strategy_discovery.py
- docs/patch_reports/PROMPT_29_4_4S2_EDGE_STRATEGY_DISCOVERY.md
- trading_bot/docs/patch_reports/PROMPT_29_4_4S2_EDGE_STRATEGY_DISCOVERY.md

Validation:
  python -m compileall -q trading_bot
  python trading_bot\test_edge_strategy_discovery.py
  python trading_bot\test_signal_risk_correctness_hardening.py
  python trading_bot\test_runtime_risk_io_hardening.py
  python trading_bot\test_probability_compression_diagnostic.py

Run analysis-only:
  python trading_bot\run_edge_strategy_discovery.py

Run full discovery matrix locally:
  python trading_bot\run_edge_strategy_discovery.py --run-backtests --windows 10000,12000,15000,18000,20000 --balance 100

Safety: diagnostic only. No live/testnet/exchange broker, no paper order submission, no forced trade generation.


## Hotfix 29.4.4s-2a

The backtest matrix runner now captures subprocess output with explicit UTF-8 decoding and `errors="replace"` to prevent Windows CP1252 `UnicodeDecodeError` crashes when child backtests print emoji, arrows, or box-drawing characters. This does not alter strategy thresholds, paper/live gates, or broker behavior.


## Hotfix 29.4.4s-2b

The backtest matrix runner now streams each child backtest output live to the console while also saving `data/edge_strategy_runs/<label>/backtest_stdout.txt`.  It runs child backtests with `python -u`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and UTF-8 `errors="replace"` decoding.  This prevents the runner from appearing frozen for several minutes on Windows and preserves per-window logs.

Expected progress markers:

```text
[EDGE DISCOVERY START] window=1/5 label=10k candles=10000 ...
... live backtest output ...
[EDGE DISCOVERY DONE] label=10k returncode=0 timed_out=False archived=...
```

Safety remains unchanged: diagnostic only; no live/testnet/exchange broker; no paper order submission; no threshold lowering; no forced trade generation.
