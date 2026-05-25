# ProgettoTR — Prompt 29.4.4r-OBS Patch Report

## Patch

`29.4.4r-OBS — 8h audit/dry-run observation`

## Scope

This patch extends the already validated observation framework after `29.4.4r — Paper order submission dry-run / simulated broker handoff`.

It is strictly observational and audit/dry-run only. It does not submit orders, does not open positions, does not call a live/testnet/exchange broker, and does not change signal, gate, risk, routing, candidate, or handoff logic.

## Main changes

- Added runner:
  - `trading_bot/run_paper_unlock_8h_observation.py`
- Extended observation aggregation in:
  - `trading_bot/core/paper_unlock_observation.py`
- Extended observation test coverage in:
  - `trading_bot/test_paper_unlock_observation.py`
- Updated 4h observation summary output to expose handoff dry-run metrics:
  - `trading_bot/run_paper_unlock_4h_observation.py`

## New report and logs

The 8h runner writes:

```text
data/paper_unlock_8h_dry_run_observation_report.json
```

Per-cycle logs are written under:

```text
data/paper_unlock_8h_observation_logs/
```

## Runner command

Recommended 8h run:

```cmd
python trading_bot\run_paper_unlock_8h_observation.py --duration-hours 8 --interval-seconds 300
```

Quick smoke test:

```cmd
python trading_bot\run_paper_unlock_8h_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1
```

Report-only aggregation:

```cmd
python trading_bot\run_paper_unlock_8h_observation.py --report-only --started-at <ISO_UTC> --ended-at <ISO_UTC>
```

## Aggregated metrics

The observation report now includes:

- runtime audit counts
- routing bridge counts
- candidate audit counts
- handoff dry-run counts
- `handoff_dry_run_events`
- `would_create_order_count`
- `broker_submit_called_count`
- `handoff_coverage_ok`
- `orders_submitted_by_handoff`
- `positions_opened_by_handoff`
- safety checks for live/testnet/exchange broker blocks

## Expected current behavior

Given the current profile has not produced `would_submit=true` / `candidate_ready=true`, the expected observation output is usually:

```text
candidate_ready_count = 0
handoff_dry_run_events = 0
would_create_order_count = 0
orders_submitted_by_handoff = 0
positions_opened_by_handoff = 0
status = PASS
```

If a future candidate becomes ready, the handoff dry-run layer may emit `PAPER_ORDER_HANDOFF_DRY_RUN`, but it must still report:

```text
would_submit_to_paper_broker = false
broker_submit_called = false
orders_submitted_by_handoff = 0
positions_opened_by_handoff = 0
```

## Safety invariants

Unchanged:

```text
operational_unlock_allowed = false
automatic_activation_allowed = false
live_allowed = false
testnet_allowed = false
exchange_broker_allowed = false
orders_submitted = 0
positions_opened = 0
orders_submitted_by_bridge = 0
orders_submitted_by_candidate_audit = 0
orders_submitted_by_handoff = 0
positions_opened_by_handoff = 0
```

## Sandbox validation

Passed:

```cmd
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```

## Next step

After local validation and an 8h run, review whether any `candidate_ready=true` or handoff dry-run events occurred. If stability remains PASS, the next roadmap item can be prepared as:

```text
29.4.4s — First real paper-only order execution, supervised
```

It must remain paper-only, supervised, and inactive unless the audited candidate/handoff prerequisites are present.
