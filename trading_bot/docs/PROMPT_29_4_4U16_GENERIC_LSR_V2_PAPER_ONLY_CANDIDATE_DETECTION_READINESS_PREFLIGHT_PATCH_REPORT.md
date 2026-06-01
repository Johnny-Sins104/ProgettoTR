# PROMPT 29.4.4u-16 — Generic LSR-v2 paper-only candidate detection readiness preflight

## Scope

This patch introduces a generic, non-ordinal LSR-v2 paper-only candidate detection readiness preflight.
It prepares the system for a later candidate detection audit without running candidate detection and without
enabling routing, handoff, submit, close, broker calls, state mutation, scheduler activity, Telegram network sends,
live mode, testnet mode, or exchange broker access.

## Added files

- `trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.py`
- `trading_bot/run_lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U16_GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U16_MANIFEST.txt`

## Readiness inputs

The preflight reads the 29.4.4u-15 parity lock report:

- `data/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json`

It requires the parity lock to be PASS and confirms:

- adapter visibility parity is locked
- lifecycle is `FLAT_LOCKED`
- open positions are zero
- pending orders are zero
- no route candidate is currently available
- no paper order intent is currently available
- LSR-v2 operator env is absent
- execution flags remain fail-closed
- source markers are present
- live/testnet/exchange broker are disabled

## Candidate readiness map

The patch emits a candidate readiness map for future generic candidate detection sources:

- paper events diagnostic read
- generic runtime snapshot artifact read
- generic order lifecycle state read
- generic re-arm policy state read
- paper state/status safety read
- strategy signal diagnostic read

All mapped stages have `execution_allowed=false` and `state_mutation_allowed=false`.

## Safety

The patch is readiness/preflight-only, read-only, and fail-closed. It explicitly keeps false:

- `generic_candidate_detection_allowed`
- `generic_candidate_scan_execution_allowed`
- `generic_route_execution_allowed`
- `generic_handoff_execution_allowed`
- `generic_submit_execution_allowed`
- `generic_close_execution_allowed`
- `paper_only_execution_allowed`
- `future_integrated_operation_allowed`
- `paper_engine_mutation_allowed`
- `runner_mutation_allowed`
- `launcher_mutation_allowed`

It also records zero orders, zero opened positions, zero closed positions, no state mutation, no scheduler start,
no Telegram network call, no live mode, no testnet mode, and no exchange broker.

## Expected local decision

`LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_READY`

## Recommended next patch

`29.4.4u-17 — Generic LSR-v2 paper-only candidate detection audit`
