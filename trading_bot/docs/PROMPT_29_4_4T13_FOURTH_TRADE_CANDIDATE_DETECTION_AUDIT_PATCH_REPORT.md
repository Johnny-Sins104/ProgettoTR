# PROMPT 29.4.4t-13 — LSR-v2 fourth-trade candidate detection audit

## Scope

This patch adds a read-only diagnostic audit for future fourth-trade LSR-v2 candidate detection.

It builds on validated `29.4.4t-12` and checks whether all upstream guarded unlock/candidate preflight artifacts are ready, then scans local diagnostic artifact logs for candidate evidence. It does not enable operational candidate detection.

## Safety contract

- No order submission.
- No position opening.
- No position closing.
- No broker call.
- No scheduler start.
- No Telegram network send.
- No paper_state mutation.
- No paper_status mutation.
- No re-entry.
- No fourth-trade unlock.
- No live/testnet/exchange broker.

## Expected local decision

`LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY`

The audit may report either no candidate or diagnostic candidate evidence. Both remain non-executing. Routing and submit stay blocked until an explicit later preflight/activation patch.
