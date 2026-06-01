# PROMPT 29.4.4u-4 — Generic LSR-v2 supervised re-arm policy draft

## Scope

Draft-only, read-only, fail-closed supervised re-arm policy for the generic LSR-v2 paper cycle.

This patch defines the reusable policy for `trade_ordinal=N` and explicitly prevents future ordinal expansion such as `fifth_trade_*`, `sixth_trade_*`, and `seventh_trade_*`.

## Added files

- `trading_bot/core/lsr_v2_supervised_rearm_policy.py`
- `trading_bot/run_lsr_v2_supervised_rearm_policy.py`
- `trading_bot/tests/test_lsr_v2_supervised_rearm_policy.py`
- `trading_bot/docs/PROMPT_29_4_4U4_GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U4_MANIFEST.txt`

## Safety

No candidate detection, route execution, submit execution, close execution, broker call, scheduler, Telegram network send, or mutation of `paper_state`/`paper_status` is allowed.

All execution flags remain false.
