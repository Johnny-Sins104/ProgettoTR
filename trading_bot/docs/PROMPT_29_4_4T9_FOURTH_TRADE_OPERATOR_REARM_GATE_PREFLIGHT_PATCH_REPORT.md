# PROMPT 29.4.4t-9 — LSR-v2 paper-only fourth-trade operator re-arm gate preflight

## Scope

This patch adds a read-only preflight for the future operator-controlled paper-only fourth-trade re-arm gate.

It introduces the operator-control model that a later unlock patch must use, but it does **not** activate the gate and does **not** unlock candidate detection, routing, submit, close, scheduler, Telegram network send, or Paper Engine execution.

## Added files

- `trading_bot/core/lsr_v2_fourth_trade_operator_rearm_gate_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_operator_rearm_gate_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_operator_rearm_gate_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T9_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T9_MANIFEST.txt`

## Operator model drafted

Future unlock patches must use explicit operator controls, currently modeled as:

- `LSR_V2_FOURTH_TRADE_REARM_ENABLE`
- `LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION`
- `LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS`
- confirmation phrase: `I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY`
- max positions: `1`

In this patch all gate permissions remain false.

## Safety contract

The patch is preflight-only/read-only:

- no submit
- no position opening
- no position close
- no broker call
- no scheduler start
- no Telegram network send
- no `paper_state` mutation
- no `paper_status` mutation
- no re-entry
- no fourth-trade unlock
- no live/testnet/exchange broker

## Expected decision

`LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY`

Expected core flags:

- `operator_rearm_gate_preflight_ready=true`
- `operator_rearm_gate_plan_ready=true`
- `operator_rearm_gate_allowed=false`
- `fourth_trade_rearm_allowed=false`
- `future_fourth_trade_unlock_allowed=false`
- `future_candidate_detection_allowed=false`
- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `paper_only_execution_allowed=false`

## Next patch

`29.4.4t-10 — LSR-v2 guarded paper-only fourth-trade operator unlock draft`
