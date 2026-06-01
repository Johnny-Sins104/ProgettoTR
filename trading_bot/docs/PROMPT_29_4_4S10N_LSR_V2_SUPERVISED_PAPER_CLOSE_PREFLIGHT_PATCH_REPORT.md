# Prompt 29.4.4s-10n — LSR-v2 supervised paper close preflight / TP-hit close boundary

## Scope

Adds a diagnostic-only close preflight for the first supervised LSR-v2 paper position. The patch reads the open-position monitor and paper state/status files, detects whether a close is required by SL/TP diagnostics, and writes close-preflight artifacts.

## Files

- `trading_bot/core/lsr_v2_supervised_paper_close_preflight.py`
- `trading_bot/run_lsr_v2_supervised_paper_close_preflight.py`
- `trading_bot/tests/test_lsr_v2_supervised_paper_close_preflight.py`

## Outputs

- `data/lsr_v2_supervised_paper_close_preflight_report.json`
- `data/lsr_v2_supervised_paper_close_preflight.jsonl`

## Decisions

- `LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_NOT_REQUIRED`
- `KEEP_DIAGNOSTIC_LSR_V2_CLOSE_DISABLED`
- `KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND`
- `KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT`
- `REJECT_LSR_V2_CLOSE_PREFLIGHT_FAILED`

## Safety invariants

- No automatic close.
- No broker close call.
- No new order.
- No new position.
- No re-entry.
- No paper-state mutation.
- No live/testnet/exchange broker.
- `would_close_position_count=0` in this patch.

## Validation

Sandbox validation:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_close_preflight.py
6 passed
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_supervised_paper_close_preflight.py trading_bot/run_lsr_v2_supervised_paper_close_preflight.py
OK
```
