# Prompt 29.4.4s-10ak — LSR-v2 third paper trade route preflight

## Scope

Adds the diagnostic route/order-intent preflight for the third supervised LSR-v2 paper trade.

The module reads:

- `data/lsr_v2_third_trade_eligibility_gate_report.json`
- `data/lsr_v2_third_trade_rearm_gate_report.json`
- `data/paper_events.jsonl`
- `data/paper_state.json`
- `data/paper_status.json`

It writes:

- `data/lsr_v2_third_trade_route_preflight_report.json`
- `data/lsr_v2_third_trade_route_preflight.jsonl`

## Required operator controls

Route preflight is route-only and requires:

```powershell
$env:LSR_V2_THIRD_TRADE_ROUTE_ENABLE="1"
$env:LSR_V2_THIRD_TRADE_ROUTE_CONFIRMATION="I_UNDERSTAND_THIRD_PAPER_TRADE_ROUTE_ONLY"
$env:LSR_V2_THIRD_TRADE_MAX_ORDERS="1"
```

## Safety invariants

This patch does not:

- submit orders
- open positions
- close positions
- call a broker
- mutate `paper_state.json`
- mutate `paper_status.json`
- enable live/testnet/exchange broker
- enable operational unlock

## Expected ready decision

```text
LSR_V2_THIRD_TRADE_ROUTE_PREFLIGHT_READY
```

with:

```text
third_trade_order_intent_ready=true
third_trade_would_route_count=1
would_create_order_count=1
would_submit_count=0
orders_submitted_by_third_trade_route_preflight=0
positions_opened_by_third_trade_route_preflight=0
```

## Validation performed in sandbox

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_third_trade_route_preflight.py
7 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_third_trade_route_preflight.py trading_bot/run_lsr_v2_third_trade_route_preflight.py
OK
```
