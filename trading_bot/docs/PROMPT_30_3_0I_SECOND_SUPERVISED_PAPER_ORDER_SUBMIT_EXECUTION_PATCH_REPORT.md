# Patch 30.3.0I - Second Supervised Paper Order Submit Execution

## Summary

This patch adds a guarded paper-only executor for the second supervised LSR-v2 order. It stays default-off until both the 30.3.0G second-order gate and the 30.3.0H bounded multi-order session readiness pass, then requires a separate execution confirmation before it can call `PaperBrokerAdapter`.

## Runtime Controls

```powershell
$env:LSR_V2_SECOND_PAPER_SUBMIT_ARM="1"
$env:LSR_V2_SECOND_PAPER_SUBMIT_CONFIRMATION="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
$env:LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE="1"
$env:LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE_CONFIRMATION="I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY"
$env:LSR_V2_SECOND_PAPER_SUBMIT_MAX_ORDERS="1"
```

## Guarantees

- Paper-only execution through `PaperBrokerAdapter`.
- Maximum one submitted order.
- Maximum one opened position.
- No live/testnet/exchange broker path.
- No automatic close.
- No automatic re-entry.
- Paper status sync after successful submit.

## Validation

Passed:

```text
python -m compileall -q trading_bot
python -m pytest trading_bot\tests\test_lsr_v2_second_paper_order_submit_execution.py trading_bot\tests\test_lsr_v2_second_paper_order_gate.py trading_bot\tests\test_lsr_v2_paper_bounded_multi_order_session.py -q
python -m pytest trading_bot\tests\test_lsr_v2_telegram_position_monitor_bridge.py trading_bot\tests\test_lsr_v2_second_trade_position_lifecycle.py trading_bot\tests\test_lsr_v2_second_paper_order_submit_execution.py -q
python tools\run_checks.py --require-deps
python -m pytest trading_bot\tests -q
```

Results:

- Targeted 30.3.0I/G/H tests: 23 passed.
- Telegram/lifecycle compatibility tests: 22 passed.
- `tools/run_checks.py --require-deps`: 30 passed.
- Full suite: 875 passed.

Runtime result:

- `data/lsr_v2_second_paper_order_submit_execution_report.json`: PASS.
- Decision: `LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED`.
- Cycle: `pc_000734_10ee70d8`.
- Orders submitted: 1.
- Positions opened: 1.
- Paper status sync: `LSR_V2_PAPER_STATUS_SYNC_APPLIED`.
- Paper state after: 2 orders, 2 positions, 1 open position.
- Paper status after: `open_positions=1`, `pending_orders=0`.

Telegram monitor:

- `data/lsr_v2_second_open_position_monitor_report.json`: PASS.
- `data/lsr_v2_telegram_position_monitor_bridge_report.json`: PASS dry-run.
- Selected notification key: `position_monitor:pc_000734_10ee70d8:BTC/USDT:98787.5000:IN_RANGE`.
- Two stale historical monitors were skipped by paper-state cycle guard.
- Telegram was not sent by this patch run because `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` were not present in the process environment.
