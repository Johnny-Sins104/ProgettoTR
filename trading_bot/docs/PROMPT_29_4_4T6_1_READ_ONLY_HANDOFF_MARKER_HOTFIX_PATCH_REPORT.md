# PROMPT 29.4.4t-6-1 — LSR-v2 read-only handoff source marker hotfix

## Scope

Hotfix for `29.4.4t-6 — Launcher/runner read-only handoff consolidation preflight`.

The validated local runner returned `WARN` with blocker `handoff_required_markers_missing` because `trading_bot/run_paper_trading.py` did not contain the literal source text marker `run_paper_trading`, even though the stable CLI handoff marker `--no-lsr-v2-engine-read-only-artifact-hook` was present and all safety/artifact checks passed.

## Change

The preflight source-marker check for `trading_bot/run_paper_trading.py` now treats the CLI flag marker as the stable required marker:

- required: `no-lsr-v2-engine-read-only-artifact-hook`
- removed overly strict literal marker: `run_paper_trading`

The patch also updates the prompt id to `29.4.4t-6-1` and adds a regression test proving that a runner source containing only the CLI hook marker is accepted.

## Safety contract

This patch is audit-only/read-only.

It does not:

- mutate launcher, runner, or engine behavior
- submit orders
- open positions
- close positions
- call brokers
- start schedulers
- send Telegram messages
- make network calls
- mutate `paper_state.json`
- mutate `paper_status.json`
- unlock re-entry
- unlock fourth trade
- enable live/testnet/exchange broker

The following remain false by design:

- `handoff_consolidation_allowed`
- `future_integrated_operation_allowed`
- `fourth_trade_rearm_allowed`
- `paper_only_execution_allowed`

## Expected local result

After installing this hotfix on the validated `29.4.4t-6` state:

```text
status=PASS
decision=LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY
read_only_handoff_preflight_ready=true
handoff_consolidation_preflight_ready=true
handoff_required_markers_present=true
missing_handoff_source_markers={}
lifecycle_state=FLAT_LOCKED
fourth_trade_locked=true
stability_lock_active=true
open_positions_after=0
paper_status_pending_orders_after=0
orders_submitted_by_read_only_handoff_preflight=0
positions_opened_by_read_only_handoff_preflight=0
positions_closed_by_read_only_handoff_preflight=0
live_enabled=false
testnet_enabled=false
exchange_broker_enabled=false
```

## Validation

Sandbox validation on the hotfix module:

```text
python -m compileall -q trading_bot
PYTHONPATH=. pytest -q trading_bot/tests/test_lsr_v2_launcher_runner_read_only_handoff_preflight.py
7 passed
```
