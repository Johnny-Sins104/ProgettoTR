# PROMPT 29.4.4t-8 — LSR-v2 paper-only fourth-trade re-arm readiness preflight

## Scope

Read-only readiness preflight for a future explicit paper-only fourth-trade re-arm patch.

This patch verifies that the validated three-trade LSR-v2 cycle remains flat and locked, that the launcher/runner/engine handoff preflight is ready, and that all candidate lifecycle inputs are available before any future re-arm gate is considered.

## Safety contract

This patch does not:

- re-arm the fourth trade
- enable candidate detection
- route candidates
- submit orders
- close positions
- call a broker
- start a scheduler
- send Telegram/network messages
- mutate paper_state.json
- mutate paper_status.json
- unlock live/testnet/exchange broker paths

All future-operation flags remain false by design.

## Added files

- `trading_bot/core/lsr_v2_fourth_trade_rearm_readiness_preflight.py`
- `trading_bot/run_lsr_v2_fourth_trade_rearm_readiness_preflight.py`
- `trading_bot/tests/test_lsr_v2_fourth_trade_rearm_readiness_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T8_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T8_MANIFEST.txt`

## Expected PASS decision

`LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY`

## Expected locked flags

- `fourth_trade_rearm_allowed=false`
- `future_fourth_trade_unlock_allowed=false`
- `future_candidate_detection_allowed=false`
- `candidate_routing_execution_allowed=false`
- `candidate_submit_execution_allowed=false`
- `paper_only_execution_allowed=false`
- `future_integrated_operation_allowed=false`

## Next patch

`29.4.4t-9 — LSR-v2 paper-only fourth-trade operator re-arm gate preflight`
