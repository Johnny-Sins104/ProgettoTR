# PROMPT 29.4.4s-10ab — LSR-v2 second supervised paper close preflight / TP-hit close boundary

## Scope
Adds a second-trade-specific close preflight after `29.4.4s-10aa` detects that the second LSR-v2 paper position reached a stop-loss or take-profit diagnostic level.

## Added files

- `trading_bot/core/lsr_v2_second_trade_close_preflight.py`
- `trading_bot/run_lsr_v2_second_trade_close_preflight.py`
- `trading_bot/tests/test_lsr_v2_second_trade_close_preflight.py`

## Artifacts

- `data/lsr_v2_second_trade_close_preflight_report.json`
- `data/lsr_v2_second_trade_close_preflight.jsonl`

## Safety

This patch is preflight-only. It does not close positions, open orders, submit to any broker, mutate paper state/status, re-enter, enable live/testnet/exchange execution, or alter risk.

Expected TP-hit state:

- `decision=LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT_READY`
- `would_prepare_close_count=1`
- `would_close_position_count=0`
- `broker_close_called=false`
- `positions_closed_by_second_trade_close_preflight=0`
