# PROMPT 29.4.4s-10f-1 — LSR-v2 operator route audit strict cycle-scope hotfix

## Scope

This patch fixes the standalone LSR-v2 operator route audit so that its counts match the current paper runtime cycle instead of being inflated by historical or duplicated diagnostic rows.

## Root cause

The paper once footer correctly counted cycle-scoped LSR-v2 runtime events from `paper_events.jsonl`, but `run_lsr_v2_operator_route_audit.py` read `lsr_v2_runtime_bridge_audit.jsonl`. That diagnostic mirror can include repeated rows because runtime artifacts are refreshed incrementally after each symbol evaluation.

## Changes

- Makes `paper_events.jsonl` the primary source for `run_lsr_v2_operator_route_audit.py`.
- Uses the latest `CYCLE_COMPLETED` event as the default cycle id.
- Filters LSR-v2 candidate/bridge events strictly by current `cycle_id`.
- Deduplicates runtime JSONL fallback rows.
- Separates current-cycle counts from historical event counts.
- Rewrites the runtime bridge diagnostic mirror with historical cycles plus deduplicated current-cycle rows.
- Updates footer/report prompt marker to `29.4.4s-10f-1`.

## Safety invariants

- `would_submit=false`
- `broker_submit_called=false`
- `routing_enabled=false`
- `execution_enabled=false`
- `paper_order_submission_enabled=false`
- `orders_submitted_by_lsr_v2_operator_route_audit=0`
- `positions_opened_by_lsr_v2_operator_route_audit=0`
- no live/testnet/exchange broker enablement
- no paper state mutation

## Validation

Sandbox validation:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_runtime_bridge_cycle_scoped.py trading_bot\tests\test_paper_once_runner_footer_lsr_v2.py trading_bot\tests\test_lsr_v2_paper_runtime_bridge_integration.py trading_bot\tests\test_lsr_v2_paper_supervised_bridge.py
python -m compileall -q trading_bot
python -m py_compile trading_bot\core\lsr_v2_runtime_bridge.py trading_bot\run_lsr_v2_operator_route_audit.py trading_bot\core\paper_once_runner_footer.py trading_bot\core\paper_once_console_summary.py
```

Observed result in sandbox: `23 passed` and compile OK.

## Expected local result

For a cycle with four scanned assets and one LSR-v2 runtime candidate ready, the standalone operator route audit should report:

```json
{
  "runtime_candidate_events": 4,
  "runtime_candidate_ready_events": 1,
  "runtime_bridge_events": 4,
  "would_route_count": 1,
  "would_submit_count": 0
}
```

Historical rows are reported separately as `historical_lsr_v2_events`, `historical_lsr_v2_candidate_events`, and `historical_lsr_v2_bridge_events`.
