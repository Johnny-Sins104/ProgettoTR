# PROMPT 29.4.4s-10q — LSR-v2 first paper trade postmortem / one-trade stability lock

## Scope

Adds a read-only postmortem layer after the first supervised LSR-v2 paper-only trade has been opened, monitored, closed, and final-audited.

The patch reconstructs the complete paper trade lifecycle and freezes the result before any further paper trading is considered.

## Added files

- `trading_bot/core/lsr_v2_first_paper_trade_postmortem.py`
- `trading_bot/run_lsr_v2_first_paper_trade_postmortem.py`
- `trading_bot/tests/test_lsr_v2_first_paper_trade_postmortem.py`
- `trading_bot/docs/PROMPT_29_4_4S10Q_FIRST_PAPER_TRADE_POSTMORTEM_PATCH_REPORT.md`

## Outputs

- `data/lsr_v2_first_paper_trade_postmortem_report.json`
- `data/lsr_v2_first_paper_trade_postmortem.jsonl`

## Expected pass decision

`LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS`

with:

- `closed_trade_complete=true`
- `postmortem_complete=true`
- `next_step_observation_required=true`
- `second_trade_allowed=false`
- `state_open_lsr_v2_positions=0`
- `paper_status_open_positions=0`
- `extra_submit_or_reentry_detected=false`
- `pnl_reconciliation_ok=true`

## Safety invariants

This patch is read-only and does not mutate paper state, submit orders, close positions, re-enter, or enable live/testnet/exchange brokerage.

Hard-coded report invariants:

- `orders_submitted_by_postmortem=0`
- `positions_opened_by_postmortem=0`
- `positions_closed_by_postmortem=0`
- `broker_submit_called_by_postmortem=false`
- `broker_close_called_by_postmortem=false`
- `paper_state_modified_by_postmortem=false`
- `paper_status_modified_by_postmortem=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`
- `second_trade_allowed=false`
- `automatic_activation_allowed=false`

## Validation

Sandbox validation passed:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_first_paper_trade_postmortem.py
6 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_first_paper_trade_postmortem.py trading_bot/run_lsr_v2_first_paper_trade_postmortem.py
OK
```

## Next step

After this postmortem passes, the next step is observation-only stability monitoring, not another submit:

`29.4.4s-10r — LSR-v2 post-first-trade observation / no-reentry stability monitor`.
