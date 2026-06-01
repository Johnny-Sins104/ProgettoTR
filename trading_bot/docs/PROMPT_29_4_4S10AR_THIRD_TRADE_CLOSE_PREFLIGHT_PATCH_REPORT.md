# Prompt 29.4.4s-10ar — LSR-v2 third trade close preflight

## Scope
Adds a third-trade-specific close preflight for the LSR-v2 paper position opened by `29.4.4s-10ao`, verified by `29.4.4s-10ap`, and monitored by `29.4.4s-10aq`.

The preflight reads the third open-position monitor, third lifecycle report, `paper_state.json`, and `paper_status.json`, then emits an auditable close boundary when SL/TP diagnostics require a close.

## Outputs
- `data/lsr_v2_third_trade_close_preflight_report.json`
- `data/lsr_v2_third_trade_close_preflight.jsonl`

## Checks
- third open-position monitor events are cycle-scoped
- exactly one open third LSR-v2 paper position is found
- paper state and paper status remain consistent
- pending orders are absent
- TP/SL diagnostics are carried forward from the monitor
- `would_prepare_close=true` only when an open matching third position has `close_required_diagnostic=true`
- `would_close_position=false` always in this patch

## Safety
Preflight-only. No close execution, no broker close call, no submit, no new order, no new position, no re-entry, no `paper_state.json` mutation, no `paper_status.json` mutation, no live/testnet/exchange broker path.

Operator environment flags are recorded but do not enable closing in this patch:

```text
LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_ENABLE=1
LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_CONFIRMATION=I_UNDERSTAND_THIRD_CLOSE_PREFLIGHT_ONLY
```

## Included hotfix
Corrects third submit execution metadata from `trade_ordinal=2` to `trade_ordinal=3` in `lsr_v2_third_trade_submit_execution.py`.

## Validation performed
- `python -m compileall -q trading_bot`
- `PYTHONPATH=trading_bot python -m pytest -q trading_bot/tests/test_lsr_v2_third_trade_close_preflight.py trading_bot/tests/test_lsr_v2_third_open_position_monitor.py trading_bot/tests/test_lsr_v2_third_trade_submit_execution.py trading_bot/test_paper_order_leakage_guard.py`
- `PYTHONPATH=trading_bot python trading_bot/run_lsr_v2_third_trade_close_preflight.py`

Observed runner result on supplied state:

```text
status=PASS
decision=LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_READY
cycle_id=pc_000505_04a050a4
open_third_lsr_v2_position_count=1
close_required_diagnostic_count=1
take_profit_hit_diagnostic_count=1
would_prepare_close_count=1
would_close_position_count=0
broker_close_called=false
positions_closed_by_third_trade_close_preflight=0
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Next step
After local validation, proceed to `29.4.4s-10as — LSR-v2 third supervised paper close execution`. That patch must remain disabled by default and require explicit operator arm/confirmation before closing exactly one paper-only position.
