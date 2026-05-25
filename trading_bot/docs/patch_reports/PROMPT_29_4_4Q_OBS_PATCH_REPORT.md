# PROMPT 29.4.4q-OBS PATCH REPORT

## Patch

`29.4.4q-OBS — 4h audit-only observation run`

## Scope

Adds a bounded observation runner and report aggregator after the validated `29.4.4q` candidate audit layer.

This patch is audit-only. It does not submit orders, open positions, enable live/testnet, enable exchange broker, alter thresholds, alter risk, alter routing, or alter signal logic.

## Added files

- `trading_bot/core/paper_unlock_observation.py`
- `trading_bot/run_paper_unlock_4h_observation.py`
- `trading_bot/test_paper_unlock_observation.py`
- `docs/patch_reports/PROMPT_29_4_4Q_OBS_PATCH_REPORT.md`
- `trading_bot/docs/patch_reports/PROMPT_29_4_4Q_OBS_PATCH_REPORT.md`

## Modified files

- `trading_bot/config.py`

## Behavior

The observation runner can run repeated `run_paper_trading.py --once --paper-unlock` cycles for a bounded duration, defaulting to 4 hours and 300 seconds between cycles.

It stores per-cycle console logs under:

```text
data/paper_unlock_observation_logs/
```

It writes an aggregate report to:

```text
data/paper_unlock_4h_observation_report.json
```

The report aggregates:

- completed cycles
- runtime audit events
- runtime accepts/rejects
- bridge events
- `would_route` / `would_submit`
- candidate audit events
- candidate ready/rejected counts
- blocked reason distributions
- map score distributions
- structure state distributions
- safety checks
- order/position counts

## Commands

Short smoke test, one cycle only:

```cmd
python trading_bot\run_paper_unlock_4h_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1
```

Full 4h observation run:

```cmd
python trading_bot\run_paper_unlock_4h_observation.py --duration-hours 4 --interval-seconds 300
```

Report-only aggregation:

```cmd
python trading_bot\run_paper_unlock_4h_observation.py --report-only
```

## Safety

Permanent safety blocks preserved:

```text
operational_unlock_allowed=false
automatic_activation_allowed=false
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
orders_submitted_by_candidate_audit=0
positions_opened_by_candidate_audit=0
```

## Validation

Sandbox tests passed:

```cmd
python trading_bot\test_paper_unlock_observation.py
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

After a clean observation report, proceed to:

```text
29.4.4r — Paper order submission dry-run / simulated broker handoff
```
