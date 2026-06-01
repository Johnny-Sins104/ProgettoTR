# PROMPT 29.4.4s-10s — LSR-v2 second supervised paper trade eligibility gate

## Scope

Read-only eligibility gate after the first LSR-v2 paper-only trade has completed, passed final audit, passed postmortem, and passed post-first-trade observation.

The gate can declare `second_trade_eligible=true` only for a future supervised flow. It does not enable execution and does not submit orders.

## Inputs

- `data/lsr_v2_post_first_trade_observation_report.json`
- `data/lsr_v2_first_paper_trade_postmortem_report.json`
- `data/lsr_v2_closed_trade_final_audit_report.json`
- `data/paper_state.json`
- `data/paper_status.json`

## Outputs

- `data/lsr_v2_second_trade_eligibility_gate_report.json`
- `data/lsr_v2_second_trade_eligibility_gate.jsonl`

## PASS criteria

- postmortem pass
- closed trade final audit pass
- observation pass
- completed observation cycles meet both 4h and 8h thresholds
- no failed or timed-out observation cycles
- no new submit cycles
- no re-entry detected
- second trade remains locked before this gate
- no open LSR-v2 paper positions
- no pending orders
- paper state/status consistency true
- realized R positive
- live/testnet/exchange/operational unlock false

## Safety invariants

- `second_trade_execute_enabled=false`
- `second_trade_submit_enabled=false`
- `broker_submit_called_by_second_trade_gate=false`
- `orders_submitted_by_second_trade_gate=0`
- `positions_opened_by_second_trade_gate=0`
- `paper_state_modified_by_second_trade_gate=false`
- `paper_status_modified_by_second_trade_gate=false`

No live, no testnet, no exchange broker, no operational unlock.
