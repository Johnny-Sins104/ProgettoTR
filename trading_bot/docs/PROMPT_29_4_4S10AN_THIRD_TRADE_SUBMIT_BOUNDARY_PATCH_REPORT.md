# Prompt 29.4.4s-10an — LSR-v2 third paper trade submit boundary

## Scope

Adds the third-trade submit boundary after `29.4.4s-10am` submit preflight. The module reads `lsr_v2_third_trade_submit_preflight_report.json` and `lsr_v2_third_trade_submit_preflight.jsonl`, then creates an audit-only submit boundary record.

## Safety

This patch is non-operational:

- no broker submit
- no order submission
- no position opening
- no position close
- no paper state mutation
- no paper status mutation
- no live mode
- no testnet mode
- no exchange broker
- `operational_unlock_allowed=false`

The boundary requires manual operator controls:

```powershell
$env:LSR_V2_THIRD_TRADE_SUBMIT_ARM="1"
$env:LSR_V2_THIRD_TRADE_SUBMIT_CONFIRMATION="I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"
$env:LSR_V2_THIRD_TRADE_MAX_ORDERS="1"
```

Even when armed, this patch does **not** submit the order. It only emits `LSR_V2_THIRD_TRADE_SUBMIT_BOUNDARY` and `LSR_V2_THIRD_SINGLE_PAPER_SUBMIT_READY_ARMED`.

## Files

- `trading_bot/core/lsr_v2_third_trade_submit_boundary.py`
- `trading_bot/run_lsr_v2_third_trade_submit_boundary.py`
- `trading_bot/tests/test_lsr_v2_third_trade_submit_boundary.py`

## Reports

- `data/lsr_v2_third_trade_submit_boundary_report.json`
- `data/lsr_v2_third_trade_submit_boundary.jsonl`

## Expected local validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_third_trade_submit_boundary.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_third_trade_submit_boundary.py --data-dir data
```

Without operator controls:

```text
KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_NOT_ARMED
orders_submitted_by_third_trade_submit_boundary=0
positions_opened_by_third_trade_submit_boundary=0
```

With operator controls:

```text
LSR_V2_THIRD_SINGLE_PAPER_SUBMIT_READY_ARMED
third_trade_submit_ready_count=1
would_submit_count=0
would_submit_to_paper_broker_count=0
orders_submitted_by_third_trade_submit_boundary=0
positions_opened_by_third_trade_submit_boundary=0
```
