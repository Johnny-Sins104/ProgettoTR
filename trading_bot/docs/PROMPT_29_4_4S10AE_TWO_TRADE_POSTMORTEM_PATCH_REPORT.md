# PROMPT 29.4.4s-10ae — LSR-v2 two-trade paper cycle postmortem / third-trade lock

## Scope

Adds a read-only, non-mutating postmortem that aggregates the first two supervised paper-only LSR-v2 trades.

The report verifies:

- first closed-trade final audit PASS;
- first-trade postmortem PASS;
- second closed-trade final audit PASS;
- exactly two submit executions and two close executions;
- combined realized PnL and realized R;
- no residual LSR-v2 paper position;
- paper_state and paper_status consistency;
- no third submit / re-entry;
- live/testnet/exchange broker remain disabled.

## New files

- `trading_bot/core/lsr_v2_two_trade_paper_cycle_postmortem.py`
- `trading_bot/run_lsr_v2_two_trade_paper_cycle_postmortem.py`
- `trading_bot/tests/test_lsr_v2_two_trade_paper_cycle_postmortem.py`

## Outputs

- `data/lsr_v2_two_trade_paper_cycle_postmortem_report.json`
- `data/lsr_v2_two_trade_paper_cycle_postmortem.jsonl`

## Expected PASS decision

`LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS`

with:

- `third_trade_allowed=false`
- `third_trade_locked=true`
- `next_step_observation_required=true`
- `orders_submitted_by_two_trade_postmortem=0`
- `positions_opened_by_two_trade_postmortem=0`
- `positions_closed_by_two_trade_postmortem=0`

## Safety

This patch never submits orders, opens positions, closes positions, mutates paper state/status, enables re-entry, or enables live/testnet/exchange broker.
