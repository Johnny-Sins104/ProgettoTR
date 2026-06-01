# PROMPT 29.4.4s-10aa — LSR-v2 second open position monitor / SL-TP tracking audit

## Scope

Adds a second-trade-specific monitor for the LSR-v2 paper position opened by `29.4.4s-10y`.

The monitor reads only second-trade lifecycle artifacts:

- `data/lsr_v2_second_trade_position_lifecycle_report.json`
- `data/lsr_v2_second_trade_position_lifecycle.jsonl`
- `data/paper_state.json`
- `data/paper_status.json`
- `data/paper_events.jsonl`

and produces:

- `data/lsr_v2_second_open_position_monitor_report.json`
- `data/lsr_v2_second_open_position_monitor.jsonl`

## Guarantees

- No new order.
- No new position.
- No close.
- No broker submit.
- No broker close.
- No paper state mutation.
- No paper status mutation.
- No re-entry.
- No live/testnet/exchange broker.

## Diagnostics

Computes:

- current price
- entry price
- stop loss
- take profit
- unrealized PnL
- current R multiple
- max/min R seen for the same position
- distance to stop
- distance to take profit
- position age
- diagnostic stop hit
- diagnostic take profit hit
- diagnostic close required

If `close_required_diagnostic=true`, the module only reports it. It does not close the position.
