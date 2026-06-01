# PROMPT 29.4.4s-10i — LSR-v2 supervised paper submit preflight / disabled-by-default broker boundary

## Scope

Adds a final disabled-by-default preflight boundary after the LSR-v2 paper broker handoff dry-run. The patch reads promotion, operator-route, order-intent and handoff dry-run artifacts, then emits `LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT` diagnostics.

## Files

- `trading_bot/core/lsr_v2_supervised_paper_submit_preflight.py`
- `trading_bot/run_lsr_v2_supervised_paper_submit_preflight.py`
- `trading_bot/tests/test_lsr_v2_supervised_paper_submit_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4S10I_LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_PATCH_REPORT.md`

## Outputs

- `data/lsr_v2_supervised_paper_submit_preflight_report.json`
- `data/lsr_v2_supervised_paper_submit_preflight.jsonl`

## Safety invariants

- `submit_enabled=false` by default and in this patch
- `would_submit=false`
- `would_submit_to_paper_broker=false`
- `broker_submit_called=false`
- `paper_order_submission_enabled=false`
- `execution_enabled=false`
- `routing_enabled=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`
- `orders_submitted_by_lsr_v2_submit_preflight=0`
- `positions_opened_by_lsr_v2_submit_preflight=0`

## Validation

Sandbox validation executed on the patch context:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_submit_preflight.py
python -m pytest -q trading_bot/tests/test_lsr_v2_supervised_paper_submit_preflight.py trading_bot/tests/test_lsr_v2_paper_broker_handoff_dry_run.py trading_bot/tests/test_lsr_v2_order_intent_audit.py trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_supervised_paper_submit_preflight.py trading_bot/run_lsr_v2_supervised_paper_submit_preflight.py
```

This patch does not call `PaperBrokerAdapter.place_order()` and does not mutate paper state.
