# Prompt 29.4.4s-2 — Edge strategy discovery / archetype performance hardening

## Scope

Diagnostic-only patch that searches for one or more strategy archetypes with validated realized edge across multiple backtest windows. It does not enable live/testnet/exchange broker, does not submit paper orders, and does not lower thresholds to force trades.

## Added

- `trading_bot/core/edge_strategy_discovery.py`
- `trading_bot/run_edge_strategy_discovery.py`
- `trading_bot/test_edge_strategy_discovery.py`

## Behavior

The runner can either analyze existing archived reports or execute a full backtest matrix.

Analysis-only:

```cmd
python trading_bot\run_edge_strategy_discovery.py
```

Full matrix with report archiving:

```cmd
python trading_bot\run_edge_strategy_discovery.py --run-backtests --windows 10000,12000,15000,18000,20000 --balance 100
```

The full matrix archives, for every window label, the generated reports under:

```text
data\edge_strategy_runs\<label>\
```

and also creates flat convenience files:

```text
data\signal_density_<label>.json
data\archetype_performance_<label>.json
data\paper_readiness_<label>.json
data\adaptive_regime_threshold_<label>.json
data\risk_event_log_<label>.json
data\risk_log_<label>.json
```

## Validation criteria

A strategy archetype is promoted to `VALID_EDGE_CANDIDATE` only if all edge requirements are met:

- enough eligible windows;
- enough positive windows;
- enough total trades;
- weighted average R above the configured minimum;
- positive total PnL;
- no unacceptable negative long-window edge;
- no forced threshold relaxation.

If no strategy satisfies the criteria, the report returns `WARN` / `KEEP_DIAGNOSTIC_NO_VALID_EDGE_STRATEGY` instead of forcing trades.

## Report

```text
data\edge_strategy_discovery_report.json
```

Key fields:

- `valid_strategies`
- `watchlist_strategies`
- `all_archetype_scores`
- `window_summary`
- `long_window_not_ready_labels`
- `readiness_positive_labels`

## Safety

This patch is diagnostic-only. It does not modify broker state, does not enable operational unlock, does not enable supervised execution, and does not affect live/testnet permissions.


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
