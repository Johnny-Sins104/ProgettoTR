# Prompt 29.4.4s-10j — LSR-v2 first supervised paper submit boundary / armed single-order gate

## Scope

Adds a supervised LSR-v2 paper submit boundary after the submit-preflight layer.
The boundary is disabled by default and requires explicit manual arming:

- `LSR_V2_PAPER_SUBMIT_ARM=1`
- `LSR_V2_PAPER_SUBMIT_CONFIRMATION=I_UNDERSTAND_SINGLE_PAPER_ORDER`
- `LSR_V2_PAPER_SUBMIT_MAX_ORDERS=1`

The CLI runner does not wire a real broker submitter, so it cannot submit orders by itself.
Actual submission is possible only if integration code explicitly injects a paper-only submitter.

## Safety

Default state:

- no live
- no testnet
- no exchange broker
- no broker call
- no order submission
- no position opening
- no paper state mutation from the standalone runner

## New files

- `core/lsr_v2_supervised_paper_submit.py`
- `run_lsr_v2_supervised_paper_submit.py`
- `tests/test_lsr_v2_supervised_paper_submit.py`

## Reports

- `data/lsr_v2_supervised_paper_submit_report.json`
- `data/lsr_v2_supervised_paper_submit.jsonl`

## Decisions

- `KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_NOT_ARMED`
- `KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_CONFIRMATION_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_PREFLIGHT_MISSING`
- `LSR_V2_SINGLE_PAPER_SUBMIT_READY_ARMED`
- `LSR_V2_SINGLE_PAPER_SUBMIT_EXECUTED`
- `REJECT_LSR_V2_SUBMIT_SAFETY_FAILED`
