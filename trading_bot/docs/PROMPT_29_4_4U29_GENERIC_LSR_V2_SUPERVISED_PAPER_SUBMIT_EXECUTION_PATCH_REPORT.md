# PROMPT 29.4.4u-29 — Generic LSR-v2 supervised paper-only submit execution

## Scope

This patch introduces a controlled/fail-closed model for future generic LSR-v2 supervised paper-only submit execution.

It consumes the validated `29.4.4u-28` order-intent activation report and checks whether the paper-only submit execution path is structurally modelable while still preventing any real broker submit in the default validation state.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_submit_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_submit_execution.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_submit_execution.py`
- `trading_bot/docs/PROMPT_29_4_4U29_GENERIC_LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U29_MANIFEST.txt`

## Design

The patch models the submit execution gate and preserves fail-closed behavior. It requires all of the following before a future real paper-only submit could be considered:

- real materialized paper order intent
- persisted paper order intent
- real submit candidate
- runtime values present and valid
- directional SL/TP validation
- re-arm operator gate
- submit operator gate
- paper-only policy
- max open positions = 1
- live/testnet/exchange disabled

In normal validation these requirements are intentionally not satisfied. Therefore the runner must report model readiness while keeping submit execution blocked.

## Safety guarantees

- No broker submit
- No broker close
- No order creation
- No order-intent persistence
- No position open/close
- No paper_state mutation
- No paper_status mutation
- No Telegram/network send
- No scheduler start
- No live/testnet/exchange path
- No ordinal trade expansion

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY`

## Expected next patch

`29.4.4u-30 — Generic LSR-v2 supervised paper open-position monitor preflight`
