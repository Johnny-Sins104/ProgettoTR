# PROMPT 29.4.4s-10h — LSR-v2 paper broker handoff dry-run / order payload schema audit

## Scope

This patch adds a diagnostic-only LSR-v2 paper-broker handoff dry-run layer after `29.4.4s-10g` order-intent audit.

It converts `LSR_V2_PAPER_ORDER_INTENT_AUDIT` rows with `would_create_order=true` into a paper-broker-compatible payload schema and emits `LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN` events.

## Files

- `trading_bot/core/lsr_v2_paper_broker_handoff_dry_run.py`
- `trading_bot/run_lsr_v2_paper_broker_handoff_dry_run.py`
- `trading_bot/tests/test_lsr_v2_paper_broker_handoff_dry_run.py`
- `trading_bot/docs/PROMPT_29_4_4S10H_LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_PATCH_REPORT.md`

## Outputs

- `data/lsr_v2_paper_broker_handoff_dry_run_report.json`
- `data/lsr_v2_paper_broker_handoff_dry_run.jsonl`

## Decisions

- `LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_NO_ORDER_INTENTS`
- `KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_NO_CREATABLE_INTENTS`
- `KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_PAYLOAD_INVALID`
- `KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_SAFETY_BLOCKED`
- `KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_ERROR`

## Safety invariants

The patch is dry-run only:

- `would_submit=false`
- `would_submit_to_paper_broker=false`
- `broker_submit_called=false`
- `paper_order_submission_enabled=false`
- `routing_enabled=false`
- `execution_enabled=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `operational_unlock_allowed=false`
- `orders_submitted_by_lsr_v2_handoff=0`
- `positions_opened_by_lsr_v2_handoff=0`

## Validation

Sandbox validation performed:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_paper_broker_handoff_dry_run.py
# 5 passed

python -m pytest -q trading_bot\tests\test_lsr_v2_paper_broker_handoff_dry_run.py trading_bot\tests\test_lsr_v2_order_intent_audit.py trading_bot\tests\test_lsr_v2_runtime_bridge_cycle_scoped.py trading_bot\tests\test_paper_once_runner_footer_lsr_v2.py trading_bot\tests\test_lsr_v2_paper_runtime_bridge_integration.py trading_bot\tests\test_lsr_v2_paper_supervised_bridge.py
# 33 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot\core\lsr_v2_paper_broker_handoff_dry_run.py trading_bot\run_lsr_v2_paper_broker_handoff_dry_run.py
```

Synthetic smoke test produced:

- `status=PASS`
- `decision=LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC`
- `handoff_dry_run_events=1`
- `payload_valid_count=1`
- `would_create_paper_order_count=1`
- `would_submit_to_paper_broker_count=0`
- `broker_submit_called=false`
- `orders_submitted_by_lsr_v2_handoff=0`
- `positions_opened_by_lsr_v2_handoff=0`

## Operator procedure

After installing, run:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_paper_broker_handoff_dry_run.py
python -m compileall -q trading_bot

$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE="1"
$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION="I_UNDERSTAND_PAPER_ONLY"

python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_lsr_v2_operator_route_audit.py --data-dir data
python trading_bot\run_lsr_v2_order_intent_audit.py --data-dir data
python trading_bot\run_lsr_v2_paper_broker_handoff_dry_run.py --data-dir data

Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE
Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION
```

This does not submit any order.
