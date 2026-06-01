# Prompt 29.4.4s-10c — LSR-v2 once footer fallback completion / runtime bridge summary visibility

## Scope

This patch fixes the operator-console visibility gap observed after `29.4.4s-10b`: the standalone LSR-v2 bridge report passed, but `run_paper_trading.py --once` used the runner hard-exit fallback footer and omitted LSR-v2 bridge metrics.

The patch is formatting/read-only only. It does not change trading gates, routing, broker state, paper state, risk sizing, signal thresholds, order submission, or position opening.

## Changes

- Adds `trading_bot/core/paper_once_runner_footer.py`.
  - Reconstructs the `--once` footer from `data/paper_events.jsonl`.
  - Loads `data/lsr_v2_paper_supervised_bridge_report.json` for LSR-v2 footer metrics.
  - Synthesizes an explicit fail-closed LSR-v2 footer block when the report is missing, instead of omitting LSR-v2 lines.
  - Force-pins all LSR-v2 execution/submission metrics to safe values before display.
- Updates `trading_bot/core/paper_once_console_summary.py` prompt marker to `29.4.4s-10c`.
- Adds `trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py`.

## Footer lines guaranteed by the runner fallback

When a `CYCLE_COMPLETED` event is available, the fallback footer now includes:

- `lsr_v2_bridge_decision`
- `lsr_v2_bridge_events`
- `lsr_v2_candidate_ready_events`
- `lsr_v2_would_route_count`
- `lsr_v2_would_submit_count=0`
- `orders_submitted_by_lsr_v2_bridge=0`
- `positions_opened_by_lsr_v2_bridge=0`

If the LSR-v2 bridge report is absent, the footer prints:

- `lsr_v2_bridge_decision=KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_REPORT_MISSING`
- all bridge counts as zero

## Safety invariants

The footer reader force-pins:

- `would_submit_count=0`
- `orders_submitted_by_lsr_v2_bridge=0`
- `positions_opened_by_lsr_v2_bridge=0`
- `broker_submit_called=false`
- `paper_order_submission_enabled=false`
- `execution_enabled=false`
- `routing_enabled=false`
- `promotion_ready=false`

No live/testnet/exchange broker path is touched.

## Validation

Sandbox validation:

```bash
python -m pytest -q trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py trading_bot/tests/test_lsr_v2_paper_runtime_bridge_integration.py trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py
# 13 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/paper_once_runner_footer.py trading_bot/core/paper_once_console_summary.py trading_bot/run_paper_trading.py
# OK
```

## Operator validation commands

```powershell
python -m pytest -q trading_bot\tests\test_paper_once_runner_footer_lsr_v2.py trading_bot\tests\test_lsr_v2_paper_runtime_bridge_integration.py trading_bot\tests\test_lsr_v2_paper_supervised_bridge.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_paper_supervised_bridge.py --data-dir data
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```

Expected footer: `prompt=29.4.4s-10c`, `footer_source=runner_event_fallback`, and the LSR-v2 bridge metric lines listed above.
