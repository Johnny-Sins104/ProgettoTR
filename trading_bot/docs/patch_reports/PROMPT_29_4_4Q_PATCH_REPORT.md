# PROMPT 29.4.4q PATCH REPORT — First guarded paper-order candidate audit

## Scope

Patch **29.4.4q** adds a guarded paper-order candidate audit layer after the existing guarded paper-only routing bridge.

The patch is diagnostic/audit-only. It does not submit broker orders, does not open positions, and does not enable live/testnet/exchange execution.

## Rationale

The validated bridge patch `29.4.4p` emits `GUARDED_PAPER_ROUTING_BRIDGE_AUDIT` events and may eventually produce `would_submit=true` when all paper-only guarded gates align. Before any paper-broker handoff can be considered, the system needs a separate candidate-order audit that records entry, stop, target, risk, size, duplicate/cadence checks, and safety state.

## Files changed

```text
trading_bot/core/paper_unlock_candidate_audit.py
trading_bot/run_paper_unlock_candidate_audit.py
trading_bot/test_paper_unlock_candidate_audit.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/config.py
trading_bot/run_paper_trading.py
docs/patch_reports/PROMPT_29_4_4Q_PATCH_REPORT.md
trading_bot/docs/patch_reports/PROMPT_29_4_4Q_PATCH_REPORT.md
```

## New event

```text
GUARDED_PAPER_ORDER_CANDIDATE_AUDIT
```

The event is emitted only when the bridge event has:

```text
would_submit = true
```

If no bridge event qualifies, candidate audit events remain zero and the report stays PASS diagnostic as long as coverage/safety checks are clean.

## Candidate audit fields

The candidate audit records:

```text
cycle_id
symbol
side
entry_price
stop_loss
take_profit
risk_per_trade_pct = 0.0025
risk_amount
position_size
notional
max_positions = 1
open_positions_count
duplicate_candle_block
duplicate_order_block
daily/weekly cadence checks
paper-only safety flags
orders_submitted_by_candidate_audit = 0
positions_opened_by_candidate_audit = 0
```

## New report

```text
data/paper_unlock_candidate_audit_report.json
```

Runner:

```cmd
python trading_bot\run_paper_unlock_candidate_audit.py
```

Expected output with no qualified bridge candidates:

```text
status = PASS
decision = PAPER_ORDER_CANDIDATE_AUDIT_READY_DIAGNOSTIC
would_submit_count = 0
candidate_order_audit_events = 0
orders_submitted_by_candidate_audit = 0
positions_opened_by_candidate_audit = 0
```

Expected output if a bridge candidate appears:

```text
would_submit_count >= 1
candidate_order_audit_events >= would_submit_count
candidate_ready_count >= 0
orders_submitted_by_candidate_audit = 0
positions_opened_by_candidate_audit = 0
```

## Safety invariants

Unchanged:

```text
operational_unlock_allowed = false
automatic_activation_allowed = false
live_allowed = false
testnet_allowed = false
exchange_broker_allowed = false
orders_submitted_by_candidate_audit = 0
positions_opened_by_candidate_audit = 0
```

No gate, risk, signal, routing, broker, live/testnet, order, or position behavior was changed.

## Validation

Sandbox tests passed:

```cmd
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```

## Local validation commands

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main

python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1

type console_once_test.txt
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"[PAPER ONCE EXIT]" console_once_test.txt

python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
python trading_bot\run_paper_unlock_candidate_audit.py
```

## Next roadmap step

After local validation, proceed to:

```text
29.4.4q-1 / 4h audit-only observation
```

or, if candidate audit coverage is stable:

```text
29.4.4r — Paper order submission dry-run / simulated broker handoff
```
