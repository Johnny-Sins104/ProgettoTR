# Prompt 29.4.4s-10b — LSR-v2 paper once runtime bridge integration / fail-closed audit

## Scope

Integrates the already validated LSR-v2 paper-supervised bridge into the paper engine artifact pipeline so a `run_paper_trading.py --once` cycle can surface LSR-v2 bridge diagnostics in the normal paper runtime event stream and once-cycle console footer.

This patch is intentionally fail-closed. It does not route orders, submit paper orders, call any broker, open positions, alter thresholds, or mutate strategy/risk gates.

## Added / changed files

- `trading_bot/core/lsr_v2_paper_supervised_bridge.py`
  - Updates prompt marker to `29.4.4s-10b`.
  - Adds `load_lsr_v2_paper_supervised_bridge_events()`.
  - Adds `prepare_lsr_v2_runtime_bridge_event()` to force-pin runtime bridge events to safe values.
- `trading_bot/core/paper_engine.py`
  - Adds `LSRV2PaperSupervisedBridgeSettings` to engine settings.
  - Adds bridge report artifact generation.
  - Mirrors bridge audit events into `paper_events.jsonl` once per cycle.
  - Adds LSR-v2 bridge report to performance artifacts.
- `trading_bot/core/paper_once_console_summary.py`
  - Adds optional LSR-v2 bridge footer lines for `--once` runs.
- `trading_bot/run_paper_trading.py`
  - Adds CLI controls to disable bridge audit or operator-enable diagnostics; submission remains disabled.
- `trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py`
  - Covers runtime event loading, forced fail-closed pinning, authorized-operator route-only diagnostics, and console footer lines.

## Safety invariants

The runtime bridge event copy enforces:

- `would_submit=false`
- `routing_enabled=false`
- `execution_enabled=false`
- `paper_order_submission_enabled=false`
- `broker_submit_called=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `orders_submitted_by_lsr_v2_runtime_bridge=0`
- `positions_opened_by_lsr_v2_runtime_bridge=0`

Even if a stale or hostile bridge event contains execution-like values, `prepare_lsr_v2_runtime_bridge_event()` overwrites them with fail-closed values.

## Runtime behavior

At the end of a paper cycle, the engine now writes:

- `data/lsr_v2_paper_supervised_bridge_report.json`
- `data/lsr_v2_paper_supervised_bridge_audit.jsonl`

It then mirrors bridge audit events into `data/paper_events.jsonl` as `LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT`, with the forced fail-closed runtime fields above. Duplicate emission is suppressed per cycle.

The `--once` footer can now include:

- `lsr_v2_bridge_decision`
- `lsr_v2_bridge_events`
- `lsr_v2_candidate_ready_events`
- `lsr_v2_would_route_count`
- `lsr_v2_would_submit_count`
- `orders_submitted_by_lsr_v2_bridge`
- `positions_opened_by_lsr_v2_bridge`

## Validation performed in sandbox

```bash
python -m pytest -q trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py
python -m compileall -q trading_bot
python -m py_compile trading_bot/core/paper_engine.py trading_bot/run_paper_trading.py
```

Result:

```text
9 passed
compileall OK
py_compile OK
```

## Operator validation commands

After extracting this patch in the project root:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_paper_runtime_bridge_integration.py trading_bot\tests\test_lsr_v2_paper_supervised_bridge.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_paper_supervised_bridge.py --data-dir data
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Expected safety result:

- `would_submit_count=0`
- `orders_submitted_by_lsr_v2_bridge=0`
- `positions_opened_by_lsr_v2_bridge=0`
- `broker_submit_called=false`
- no paper order or position is created by LSR-v2 bridge integration.

## Next step

If local once-cycle validation shows LSR-v2 bridge events in the runtime event log and footer while all submit/order/position counters remain zero, the next patch can be a supervised dry-run candidate-to-paper-order lifecycle audit. It should still be operator-controlled and fail-closed by default.
