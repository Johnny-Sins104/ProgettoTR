# PROMPT 29.4.4s-10f — LSR-v2 operator-controlled would-route audit / submit still blocked

## Scope

This patch extends the LSR-v2 runtime cycle bridge with explicit operator-controlled would-route diagnostics while preserving the fail-closed paper-supervised boundary.

The patch verifies that an approved runtime LSR-v2 candidate can advance from `candidate_ready=true` to `would_route=true` only when all manual operator controls are present. It still force-blocks submit, broker calls, order creation, position opening, live, testnet, and exchange broker paths.

## Changed files

- `trading_bot/core/lsr_v2_paper_supervised_bridge.py`
  - Adds operator env aliases:
    - `LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE`
    - `LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION`
    - `LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION_PHRASE`
  - Keeps bridge-prefixed config names backward compatible.
  - Accepts `I_UNDERSTAND_PAPER_ONLY` and the legacy LSR-v2 phrase.
  - Keeps `would_submit=false` hard-coded.

- `trading_bot/core/lsr_v2_runtime_bridge.py`
  - Adds operator route audit report/jsonl:
    - `data/lsr_v2_operator_route_audit_report.json`
    - `data/lsr_v2_operator_route_audit.jsonl`
  - Summarizes `operator_enable`, `operator_confirmation_ok`, `operator_authorized`, `would_route_count`, and submit-blocked safety fields.
  - Writes operator route artifacts during runtime bridge artifact refresh.

- `trading_bot/core/paper_once_runner_footer.py`
  - Counts operator fields from cycle-scoped `paper_events.jsonl`.
  - Keeps event-log fallback as source of truth for watchdog footer.

- `trading_bot/core/paper_once_console_summary.py`
  - Prints:
    - `lsr_v2_operator_enable=`
    - `lsr_v2_operator_confirmation_ok=`

- `trading_bot/core/paper_engine.py`
  - Bumps prompt marker to `29.4.4s-10f` for the LSR-v2 runtime bridge integration.

- `trading_bot/run_lsr_v2_operator_route_audit.py`
  - New offline runner to summarize route audit from cycle-scoped runtime events.

- Tests updated/added:
  - `trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py`
  - `trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py`
  - `trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py`

## Operator controls

Manual route diagnostics require:

```text
LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE=1
LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION=I_UNDERSTAND_PAPER_ONLY
```

If these are absent, the runtime bridge remains:

```text
would_route=false
would_submit=false
blocked_reason=operator_disabled / operator_confirmation_missing
```

If present and a runtime LSR-v2 candidate is ready, the runtime bridge can become:

```text
would_route=true
would_submit=false
blocked_reason=paper_supervised_bridge_fail_closed
```

## Safety invariants

The patch force-pins:

```text
would_submit=false
broker_submit_called=false
routing_enabled=false
execution_enabled=false
paper_order_submission_enabled=false
orders_submitted_by_lsr_v2_runtime_bridge=0
positions_opened_by_lsr_v2_runtime_bridge=0
orders_submitted_by_lsr_v2_operator_route_audit=0
positions_opened_by_lsr_v2_operator_route_audit=0
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
promotion_ready=false
```

## Validation performed in sandbox

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py trading_bot/tests/test_liquidity_sweep_reversal_v2.py
```

Result:

```text
28 passed
```

Compilation:

```text
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_runtime_bridge.py trading_bot/core/lsr_v2_paper_supervised_bridge.py trading_bot/core/paper_once_runner_footer.py trading_bot/core/paper_once_console_summary.py trading_bot/run_lsr_v2_operator_route_audit.py
```

Result: OK.

## Expected local validation

Default/operator disabled:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Operator would-route diagnostic:

```powershell
$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE="1"
$env:LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION="I_UNDERSTAND_PAPER_ONLY"
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
python trading_bot\run_lsr_v2_operator_route_audit.py --data-dir data
Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE
Remove-Item Env:\LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION
```

Expected if a runtime candidate-ready event appears during the operator run:

```text
lsr_v2_runtime_would_route_count>=1
lsr_v2_runtime_would_submit_count=0
orders_submitted_by_lsr_v2_runtime_bridge=0
positions_opened_by_lsr_v2_runtime_bridge=0
```

## Decision

`29.4.4s-10f` remains audit-only. It is a route-readiness diagnostic, not execution enablement.
