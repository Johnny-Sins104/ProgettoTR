# Prompt 29.4.4u-33 — Generic LSR-v2 supervised paper close execution

## Scope

This patch adds a controlled, paper-only close execution gate/model for the generic LSR-v2 path. It consumes the validated `29.4.4u-32` close execution scaffold report and evaluates whether a real paper close could be attempted in a future activation path.

## Expected validation behaviour

The normal validation state remains fail-closed:

- no broker submit receipt is available;
- no real paper position is open;
- the open-position monitor is not ready;
- no close trigger is available;
- re-arm, submit, and close operator gates are absent;
- runtime values are still deferred;
- no broker submit/close call is made;
- no `paper_state` / `paper_status` mutation occurs;
- no scheduler or Telegram/network send occurs;
- live/testnet/exchange broker access remains disabled.

The runner should therefore return `PASS` with decision `LSR_V2_GENERIC_SUPERVISED_PAPER_CLOSE_EXECUTION_READY`, while all real close execution flags remain false.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_close_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_close_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_close_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U33_GENERIC_LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U33_MANIFEST.txt`

## Safety guarantees

This patch does not close positions, does not call the paper broker, does not submit orders, does not reconcile realized PnL, does not run final audit/postmortem execution, does not mutate state, and does not enable live/testnet/exchange execution.

## Next patch

`29.4.4u-34 — Generic LSR-v2 supervised paper realized PnL reconciliation preflight`.
