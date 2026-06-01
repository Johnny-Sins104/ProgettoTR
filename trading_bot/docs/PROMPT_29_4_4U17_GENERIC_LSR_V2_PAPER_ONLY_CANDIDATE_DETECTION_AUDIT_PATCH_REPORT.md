# PROMPT 29.4.4u-17 — Generic LSR-v2 paper-only candidate detection audit

## Scope

This patch adds a generic, non-ordinal, paper-only candidate detection audit.
It builds on `29.4.4u-16` candidate detection readiness preflight and performs
only diagnostic reads of the mapped candidate sources.

## Files

- `trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_audit.py`
- `trading_bot/run_lsr_v2_generic_paper_only_candidate_detection_audit.py`
- `trading_bot/tests/test_lsr_v2_generic_paper_only_candidate_detection_audit.py`

## Behavior

The audit reads candidate-related sources mapped by u-16:

- paper events JSONL diagnostic read
- generic runtime snapshot artifact read
- generic order lifecycle state read
- generic re-arm policy state read
- paper state/status safety read
- strategy signal diagnostic read

It may set diagnostic fields such as:

- `candidate_detected_diagnostic`
- `candidate_detected_diagnostic_count`
- `candidate_detection_source_counts`
- `candidate_diagnostic_examples`

These fields are diagnostic only and do not route or submit anything.

## Safety

The patch is audit-only, read-only, and fail-closed:

- no route execution
- no handoff execution
- no submit execution
- no close execution
- no broker call
- no scheduler start
- no Telegram network send
- no paper state/status mutation
- no live/testnet/exchange broker
- no ordinal expansion

## Expected decision

`LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT_READY`
