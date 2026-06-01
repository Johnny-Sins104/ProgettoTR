# PROMPT 29.4.4t-10 — LSR-v2 guarded paper-only fourth-trade operator unlock draft

## Scope

This patch adds a guarded, fail-closed operator unlock draft for a future paper-only fourth-trade re-arm.

It validates the already-passed `29.4.4t-9` operator re-arm gate preflight, models the exact operator env controls, and reports whether those controls are absent, invalid, or valid for a later activation patch.

This patch does **not** unlock the fourth trade and does **not** enable candidate detection, routing, submit, close, scheduler, Telegram network send, or Paper Engine candidate execution.

## Added files

- `trading_bot/core/lsr_v2_fourth_trade_operator_unlock_draft.py`
- `trading_bot/run_lsr_v2_fourth_trade_operator_unlock_draft.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_operator_unlock_draft.py`
- `trading_bot/docs/PROMPT_29_4_4T10_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T10_MANIFEST.txt`

## Operator model

The draft validates this future operator control model:

- `LSR_V2_FOURTH_TRADE_REARM_ENABLE=1`
- `LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION=I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY`
- `LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS=1`

If these controls are present and correct, the report may set:

- `operator_unlock_draft_armed=true`
- `operator_unlock_controls_valid_for_future_patch=true`
- `operator_unlock_would_rearm_fourth_trade=true`

But all actual execution permissions remain false.

## Safety contract

The patch is draft-only/read-only:

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
- no candidate detection activation
- no live/testnet/exchange broker

## Expected decision

`LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY`

Expected core flags:

- `operator_unlock_draft_ready=true`
- `guarded_operator_unlock_draft_ready=true`
- `operator_unlock_allowed=false`
- `fourth_trade_rearm_allowed=false`
- `future_candidate_detection_allowed=false`
- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `paper_only_execution_allowed=false`

## Next patch

`29.4.4t-11 — LSR-v2 guarded paper-only fourth-trade operator unlock activation preflight`
