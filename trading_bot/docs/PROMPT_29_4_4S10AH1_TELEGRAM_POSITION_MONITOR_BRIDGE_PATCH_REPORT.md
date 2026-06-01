# PROMPT 29.4.4s-10ah-1 — LSR-v2 Telegram open-position monitor bridge / SL-TP progress bar

## Scope

Adds a read-only Telegram bridge for LSR-v2 open paper positions.  The bridge reads existing open-position monitor artifacts and formats a Telegram message with a textual SL/TP line and a moving marker:

```text
SL 72568.30 ┃━━━━━━●──────────┃ TP 73178.31
```

The marker is calculated from the current price relative to stop loss and take profit, with BUY and SELL semantics handled separately.

## Files

```text
trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py
trading_bot/run_lsr_v2_telegram_position_monitor_bridge.py
trading_bot/tests/test_lsr_v2_telegram_position_monitor_bridge.py
```

## Inputs

The bridge can read:

```text
data/lsr_v2_open_position_monitor_report.json
data/lsr_v2_open_position_monitor.jsonl
data/lsr_v2_second_open_position_monitor_report.json
data/lsr_v2_second_open_position_monitor.jsonl
data/lsr_v2_third_open_position_monitor_report.json
data/lsr_v2_third_open_position_monitor.jsonl
```

## Outputs

```text
data/lsr_v2_telegram_position_monitor_bridge_report.json
data/lsr_v2_telegram_position_monitor_bridge.jsonl
data/lsr_v2_telegram_position_monitor_bridge_state.json
data/telegram_audit.jsonl
```

## Telegram message fields

Each open-position monitor message includes:

```text
symbol
side
entry_price
current_price
stop_loss
take_profit
SL/TP progress bar with moving marker
progress_to_TP percentage
status zone / TP-hit / SL-hit diagnostic
percent distance to SL
percent distance to TP
unrealized PnL
R multiple
cycle_id
```

## Operator controls

Dry-run is default.  Real Telegram send requires:

```text
--send
--confirmation "I_UNDERSTAND_SEND_LSR_V2_POSITION_MONITOR"
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

Optional:

```text
--force-resend
--max-messages 3
--bar-width 24
```

## Safety invariants

The bridge is observability-only:

```text
no order submit
no position open
no position close
no broker submit
no broker close
no paper_state mutation
no paper_status mutation
no live
no testnet
no exchange broker
no operational unlock
```

## Validation

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_telegram_position_monitor_bridge.py
7 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py trading_bot/run_lsr_v2_telegram_position_monitor_bridge.py
OK
```
