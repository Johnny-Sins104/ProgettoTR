# Prompt 29.4.4s-OBS — Supervised inactive observation / candidate exposure monitor

## Scope

This patch adds a dedicated supervised-inactive observation wrapper after `29.4.4s`. It observes the full guarded chain while operator execution remains disabled.

The monitored chain is:

```text
GUARDED_PAPER_RUNTIME_AUDIT
→ GUARDED_PAPER_ROUTING_BRIDGE_AUDIT
→ GUARDED_PAPER_ORDER_CANDIDATE_AUDIT
→ PAPER_ORDER_HANDOFF_DRY_RUN
→ PAPER_SUPERVISED_ORDER_EXECUTION
```

## Safety contract

The observation is valid only when all of the following remain true:

```text
operator_enable=false
operator_confirmation_ok=false
supervised_submit_allowed_count=0
supervised_broker_submit_called_count=0
broker_submit_called_count=0
orders_submitted_by_supervised=0
positions_opened_by_supervised=0
orders_submitted=0
positions_opened=0
legacy_order_leakage_detected=false
unauthorized_orders_count=0
unauthorized_positions_opened_count=0
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
```

Candidate exposure is allowed and explicitly measured. A future `candidate_ready=true` or `would_create_order=true` should not execute an order while this observation remains inactive.

## Files added

```text
trading_bot/core/paper_unlock_supervised_inactive_observation.py
trading_bot/run_paper_unlock_supervised_inactive_observation.py
trading_bot/test_paper_unlock_supervised_inactive_observation.py
docs/patch_reports/PROMPT_29_4_4S_OBS_PATCH_REPORT.md
trading_bot/docs/patch_reports/PROMPT_29_4_4S_OBS_PATCH_REPORT.md
PATCH_ONLY_README_29_4_4S_OBS.txt
```

## Files modified

```text
trading_bot/config.py
```

## Report path

```text
data/paper_unlock_supervised_inactive_observation_report.json
```

## Log path

```text
data/paper_unlock_supervised_inactive_observation_logs/
```

## Validation commands

```cmd
python trading_bot\test_paper_unlock_supervised_inactive_observation.py
python trading_bot\test_paper_unlock_supervised_execution.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_legacy_position_quarantine.py
python -m compileall -q trading_bot
```

## Local smoke test

```cmd
python trading_bot\run_paper_unlock_supervised_inactive_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1
```

Expected inactive result:

```text
status=PASS
supervised_submit_allowed_count=0
broker_submit_called_count=0
orders_submitted=0
positions_opened=0
operator_enable=false
operator_confirmation_ok=false
```

## No operational changes

This patch does not change strategy thresholds, signal generation, risk, routing, broker behavior, live/testnet settings, or legacy execution guard. It only adds a stricter inactive observation/report wrapper.
