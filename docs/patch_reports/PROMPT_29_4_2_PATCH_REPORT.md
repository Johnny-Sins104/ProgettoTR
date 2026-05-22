# Prompt 29.4.2 — Signal density diagnostics + conservative entry unlock analysis

## Scope

This patch adds diagnostic-only paper signal-density visibility. It does not change the strategy, thresholds, risk sizing, paper/live mode, broker execution, or Telegram safety controls.

## Added

- `trading_bot/core/paper_signal_diagnostics.py`
- `data/paper_signal_diagnostics_report.json` generated at runtime
- `SIGNAL_DIAGNOSTIC` event emitted for each scanned asset/candle
- Dominant rejection filters:
  - `TECH_SCORE_LOW`
  - `NO_TECHNICAL_CANDIDATE`
  - `RANGE_POSITION_FILTERED`
  - `TREND_ALIGNMENT_FILTERED`
  - `MTF_FILTERED`
  - `META_PROB_LOW`
  - `SETUP_QUALITY_LOW`
  - `META_FILTERED`
  - `DUPLICATE_CANDLE`
  - `ACCEPTED`
- Diagnostic asset table and dominant filters in dashboard/performance report
- `/report` now exposes signal diagnostics and unlock status

## Safety guarantees

- `PAPER_ENTRY_UNLOCK_ENABLED=0` by default.
- Exploratory candidates are analysis-only.
- No signal is force-enabled.
- No threshold is lowered operationally.
- Live/testnet execution remains blocked.

## New environment values

```env
PAPER_SIGNAL_DIAGNOSTICS_ENABLED=1
PAPER_SIGNAL_DIAGNOSTICS_REPORT_PATH=data/paper_signal_diagnostics_report.json
PAPER_EXPLORATORY_SIGNAL_ANALYSIS=1
PAPER_EXPLORATORY_META_PROB_THRESHOLD=48.0
PAPER_EXPLORATORY_RANGING_META_PROB_THRESHOLD=45.0
PAPER_EXPLORATORY_MIN_SETUP_QUALITY=60.0
PAPER_ENTRY_UNLOCK_ENABLED=0
```

## Validation

Run:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once
type data\paper_signal_diagnostics_report.json
type data\paper_performance_report.json
```

Expected:

- `SIGNAL_DIAGNOSTIC` events in `data/paper_events.jsonl`.
- `paper_signal_diagnostics_report.json` exists.
- `diagnostic_only=true`.
- `strategy_changed=false`.
- `paper_entry_unlock_enabled=false` in `paper_status.json`.
