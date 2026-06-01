# PROMPT 29.4.4u-32 — Generic LSR-v2 supervised paper close execution scaffold

## Scope

This patch introduces a scaffold-only, read-only, fail-closed model for future generic LSR-v2 paper-only close execution.

## Files

- `trading_bot/core/lsr_v2_generic_supervised_paper_close_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_close_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_close_execution_scaffold.py`
- `trading_bot/docs/PROMPT_29_4_4U32_GENERIC_LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION_SCAFFOLD_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U32_MANIFEST.txt`

## Upstream

Consumes `data/lsr_v2_generic_supervised_paper_close_preflight_report.json` from `29.4.4u-31`.

## Safety

The scaffold never closes a position, never calls a broker, never submits, never starts schedulers, never sends Telegram/network messages, and never mutates `paper_state` or `paper_status`.

Expected validation state remains fail-closed:

- `broker_submit_receipt_available=false`
- `paper_open_position_available=false`
- `paper_position_open=false`
- `paper_open_position_monitor_ready=false`
- `close_trigger_available=false`
- `generic_close_execution_allowed=false`
- `paper_close_execution_ready=false`
- `broker_close_allowed=false`
- `would_prepare_close=false`
- `would_call_paper_broker_close=false`
- `would_close=false`
- `would_submit=false`

## Expected validation

```text
compileall: PASS
pytest u32 + u31 + ... + u20: PASS
runner: PASS
decision: LSR_V2_GENERIC_SUPERVISED_PAPER_CLOSE_EXECUTION_SCAFFOLD_READY
```

## Next patch

`29.4.4u-33 — Generic LSR-v2 supervised paper close execution`
