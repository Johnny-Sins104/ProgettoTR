# Prompt 29.4.4s-10g — LSR-v2 paper order intent audit / submit preflight dry-run

## Scope

Adds a diagnostic LSR-v2 paper-order intent layer after the operator-controlled runtime bridge.

The layer reads strict cycle-scoped LSR-v2 runtime bridge events, selects only rows with `would_route=true`, and builds `LSR_V2_PAPER_ORDER_INTENT_AUDIT` events containing paper-order intent fields:

- `cycle_id`
- `symbol`
- `side`
- `profile_name`
- `selected_overlay_id`
- `entry_price`
- `stop_loss`
- `take_profit`
- `risk_per_trade_pct`
- `risk_amount`
- `position_size`
- `notional`
- `max_positions`
- duplicate/cadence diagnostic checks
- `would_create_order`
- `would_submit=false`
- `broker_submit_called=false`

## Safety invariants

This patch is fail-closed and diagnostic-only:

- no live
- no testnet
- no exchange broker
- no broker call
- no order submission
- no position opening
- no paper state mutation
- `would_submit=false`
- `paper_order_submission_enabled=false`
- `orders_submitted_by_lsr_v2_order_intent=0`
- `positions_opened_by_lsr_v2_order_intent=0`

## Added files

- `trading_bot/core/lsr_v2_order_intent_audit.py`
- `trading_bot/run_lsr_v2_order_intent_audit.py`
- `trading_bot/tests/test_lsr_v2_order_intent_audit.py`

## Outputs

- `data/lsr_v2_order_intent_audit_report.json`
- `data/lsr_v2_order_intent_audit.jsonl`

## Expected decisions

- `LSR_V2_ORDER_INTENT_AUDIT_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_NO_WOULD_ROUTE`
- `KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_NO_RUNTIME_EVENTS`
- `KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_INVALID_LEVELS`
- `KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_SAFETY_BLOCKED`

## Local validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_order_intent_audit.py
python -m compileall -q trading_bot

$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE="1"
$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION="I_UNDERSTAND_PAPER_ONLY"
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_lsr_v2_operator_route_audit.py --data-dir data
python trading_bot\run_lsr_v2_order_intent_audit.py --data-dir data
Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE
Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION
```
