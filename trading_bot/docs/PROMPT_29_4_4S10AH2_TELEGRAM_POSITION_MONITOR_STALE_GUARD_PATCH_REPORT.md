# Prompt 29.4.4s-10ah-2 — LSR-v2 Telegram position monitor stale-open guard

## Scope

Hotfix for `29.4.4s-10ah-1` Telegram open-position monitor bridge.

The bridge now prevents stale Telegram monitor messages when an older open-position monitor report still says a position is open after a supervised close execution already closed it.

## Changes

- Updates `core/lsr_v2_telegram_position_monitor_bridge.py` prompt id to `29.4.4s-10ah-2`.
- Adds stale-open guard using:
  - `paper_status.json`
  - `paper_state.json`
  - `lsr_v2_supervised_paper_close_execution_report.json`
  - `lsr_v2_second_trade_close_execution_report.json`
  - future-compatible `lsr_v2_third_trade_close_execution_report.json`
- Skips monitor notifications when:
  - `paper_status.open_positions == 0`
  - no open LSR-v2 position exists in `paper_state.json`
  - the monitor cycle was already closed by a close-execution report
- Adds report diagnostics:
  - `stale_guard`
  - `stale_monitor_skipped_count`
  - `stale_monitor_skipped_reasons`
  - `stale_monitor_skipped_keys`
- Extends unit tests for stale monitor suppression after second close execution.

## Safety

Observation only. No trading side effects.

- No submit
- No close
- No broker call
- No `paper_state.json` mutation
- No `paper_status.json` mutation
- No live
- No testnet
- No exchange broker

## Validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_telegram_position_monitor_bridge.py
# 8 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot\core\lsr_v2_telegram_position_monitor_bridge.py trading_bot\run_lsr_v2_telegram_position_monitor_bridge.py
```

## Expected local behavior after second trade is closed

```text
status=PASS
decision=KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_NO_OPEN_POSITION
open_position_candidate_count=0
stale_monitor_skipped_count>=1
telegram_send_attempted_count=0
```

If a future third paper trade is actually open and `paper_status.open_positions > 0`, the bridge can send the SL/TP progress monitor normally.
