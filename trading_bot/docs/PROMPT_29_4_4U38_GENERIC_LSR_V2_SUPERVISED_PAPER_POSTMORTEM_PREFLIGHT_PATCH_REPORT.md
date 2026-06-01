# Prompt 29.4.4u-38 — Generic LSR-v2 supervised paper postmortem preflight

## Scope
Adds a paper-only, read-only, fail-closed postmortem preflight model that consumes the validated `29.4.4u-37` final-audit execution artifact.

## Files
- `trading_bot/core/lsr_v2_generic_supervised_paper_postmortem_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_postmortem_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_postmortem_preflight.py`

## Safety guarantees
The patch does not execute a postmortem, does not mutate paper state/status, does not submit or close, does not call any broker, does not start a scheduler, does not send Telegram/network messages, and does not enable live/testnet/exchange access.

In the expected validation state it returns `LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_PREFLIGHT_READY` while preserving `generic_postmortem_execution_allowed=false`, `paper_postmortem_ready=false`, `would_run_postmortem=false`, and all broker/state/network/scheduler guards disabled.

## Next patch
`29.4.4u-39 — Generic LSR-v2 supervised paper postmortem execution scaffold`.
