# Prompt 29.4.4s-10ai — External fixes selective merge + candlestick conflict hardening

## Scope

Selective patch for the original project, using the externally modified copy only as an audit source.

## Included changes

- `core/correlation_engine.py`
  - Replaces deprecated `fillna(method=...)` path with method dispatch when available.
  - Replaces direct diagonal mutation through `.values` with `.iloc` assignment.

- `core/notifier.py`
  - Adds safe cancellation/await of the legacy polling task on `close()`.
  - Handles `asyncio.CancelledError` explicitly in polling.
  - Clears `_polling_task` in `finally`.

- `main.py`
  - Adds bounded `append_to_log_with_rotation()` for `data/bot_live.log`.
  - Routes live black-box log writes through the rotation helper.
  - Keeps live indicator calls as `TechnicalAnalyzer().add_indicators(df, is_live=True)`.
  - Closes the legacy notifier only at main shutdown.

- `core/candlestick_patterns.py`
  - Makes the directional conflict score cap explicit via `DIRECTIONAL_CONFLICT_SCORE_CAP`.
  - Adds conflict diagnostics to `context`.
  - Ensures simultaneous bullish/bearish candlestick patterns remain neutralized.

- `tests/test_external_selective_merge.py`
  - Covers fake breakdown + fake breakout simultaneous conflict.
  - Covers correlation diagonal/fill behavior.
  - Covers notifier polling-task close safety.
  - Static-checks `main.py` log rotation and `is_live=True` preservation.

## Explicitly not changed

- LSR-v2 paper execution gates.
- Paper broker submit/close logic.
- `paper_state.json` / `paper_status.json` mutation logic.
- Telegram LSR-v2 notification bridges.
- Two-trade postmortem/observation logic.
- Live/testnet/exchange broker flags.

## Safety intent

This is a corrective merge, not a trading expansion. It must not enable third-trade execution, live mode, testnet mode, or exchange broker execution.

## Suggested validation

```powershell
python -m pytest -q trading_bot\tests\test_external_selective_merge.py
python -m pytest -q trading_bot\tests\test_lsr_v2_two_trade_observation.py trading_bot\tests\test_lsr_v2_telegram_position_monitor_bridge.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_two_trade_observation.py --data-dir data
python trading_bot\run_lsr_v2_telegram_position_monitor_bridge.py --data-dir data
```

Expected LSR-v2 state after patch:

- `LSR_V2_TWO_TRADE_OBSERVATION_PASS`
- `third_trade_locked=true`
- `paper_status_open_positions=0`
- `KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_NO_OPEN_POSITION`
