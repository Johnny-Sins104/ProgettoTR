# Prompt 29.4.4u-47 — Generic LSR-v2 supervised paper terminal lifecycle handoff preflight

## Scope

This patch adds a terminal lifecycle handoff preflight checkpoint for the generic LSR-v2 supervised paper lifecycle.

It consumes the `29.4.4u-46` lifecycle state/status completion mutation execution report and models the future terminal handoff gate without enabling any real terminal handoff, state/status mutation, Telegram send, scheduler start, broker call, submit, close, live, testnet, or exchange access.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U47_GENERIC_LSR_V2_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U47_MANIFEST.txt`

## Expected validation state

The expected local validation state has no completed runtime lifecycle evidence:

- no broker submit receipt
- no broker close receipt
- no real close execution
- no closed paper position
- no realized-PnL write
- no final audit runtime execution
- no postmortem runtime execution
- no lifecycle completion audit runtime execution
- no lifecycle state/status completion mutation runtime
- no terminal handoff runtime
- no operator gates
- no runtime values

Therefore the patch returns a PASS/ready diagnostic for the preflight model while keeping all execution and mutation outputs fail-closed.

## Required invariants

- `generic_terminal_lifecycle_handoff_allowed=false`
- `generic_terminal_lifecycle_handoff_execution_allowed=false`
- `paper_terminal_lifecycle_handoff_ready=false`
- `would_handoff_terminal_lifecycle=false`
- `would_mutate_paper_state=false`
- `would_mutate_paper_status=false`
- `would_send_telegram=false`
- `would_start_scheduler=false`
- `would_submit=false`
- `would_close=false`
- no broker calls
- no paper state/status mutation
- no scheduler start
- no Telegram network send
- no live/testnet/exchange access
- no ordinal expansion

## Next patch

`29.4.4u-48 — Generic LSR-v2 supervised paper terminal lifecycle handoff execution scaffold`
