# PROMPT 29.4.4r — Paper order submission dry-run / simulated broker handoff

## Scope

Adds an audit-only simulated handoff layer after `GUARDED_PAPER_ORDER_CANDIDATE_AUDIT`.
The layer emits `PAPER_ORDER_HANDOFF_DRY_RUN` only when a candidate audit event is already `candidate_ready=true`.

## Safety

No broker call is made. The patch does not submit orders, does not open positions, does not enable live/testnet, and does not enable an exchange broker.

Permanent safety fields remain fail-closed:

```text
operational_unlock_allowed=false
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
broker_submit_called=false
orders_submitted_by_handoff=0
positions_opened_by_handoff=0
```

## Files changed

```text
trading_bot/core/paper_unlock_handoff_dry_run.py
trading_bot/run_paper_unlock_handoff_dry_run.py
trading_bot/test_paper_unlock_handoff_dry_run.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/config.py
trading_bot/run_paper_trading.py
docs/patch_reports/PROMPT_29_4_4R_PATCH_REPORT.md
trading_bot/docs/patch_reports/PROMPT_29_4_4R_PATCH_REPORT.md
PATCH_ONLY_README_29_4_4R.txt
```

## Runtime behavior

The handoff dry-run layer is inactive when no candidate-ready event exists.
On current 4h observation data, the report returns PASS with zero candidate-ready and zero handoff events.

Expected current result:

```text
status=PASS
decision=PAPER_ORDER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC
candidate_ready_count=0
handoff_dry_run_events=0
would_create_order_count=0
orders_submitted_by_handoff=0
positions_opened_by_handoff=0
```

If a future candidate is ready, the patch emits a diagnostic `PAPER_ORDER_HANDOFF_DRY_RUN` event with `would_create_order=true`, while still keeping `would_submit_to_paper_broker=false` and `broker_submit_called=false`.

## Tests run

```cmd
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```

All passed in sandbox.
