# PROMPT 29.4.4s-10ae-1 — Two-trade postmortem closed-position reconciliation hotfix

## Scope

Hotfix for `29.4.4s-10ae` two-trade paper-cycle postmortem. The previous postmortem required `paper_state.json` to expose at least two closed LSR-v2 positions. Local validation showed that the paper state may retain only the latest closed LSR-v2 position even when both cycle-scoped final audits are PASS and both close executions are present.

## Change

`paper_state.json` is no longer treated as the authoritative closed-position history. It remains a residual exposure guard only:

- `state_open_lsr_v2_positions` must be zero.
- `paper_status_open_positions` must be zero.
- `paper_status_pending_orders` must be zero.
- First and second closed-trade final audit reports remain the authoritative source for closed trade count, realized PnL, realized R, submit count, and close count.

New diagnostic fields:

- `paper_state_closed_history_complete`
- `paper_state_closed_history_source_is_authoritative=false`
- `paper_state_closed_history_note`

## Expected decision

The postmortem may now return:

```text
LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS
```

when:

```text
first_closed_trade_final_audit_pass=true
second_closed_trade_final_audit_pass=true
submit_execution_events_total=2
close_execution_events_total=2
pnl_reconciliation_ok=true
residual_open_position=false
paper_status_open_positions=0
paper_status_pending_orders=0
third_submit_or_reentry_detected=false
```

even if:

```text
state_closed_lsr_v2_positions=1
paper_state_closed_history_complete=false
```

## Safety

No orders, no closes, no broker calls, no state mutation, no status mutation, no live, no testnet, no exchange broker.

## Validation

Sandbox:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_two_trade_paper_cycle_postmortem.py
7 passed
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_two_trade_paper_cycle_postmortem.py trading_bot/run_lsr_v2_two_trade_paper_cycle_postmortem.py
OK
```
