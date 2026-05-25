# PROMPT 29.4.4s — First real paper-only order execution, supervised

## Scope

Adds the first intentionally supervised paper-only execution boundary after the guarded path:

`GUARDED_PAPER_RUNTIME_AUDIT -> GUARDED_PAPER_ROUTING_BRIDGE_AUDIT -> GUARDED_PAPER_ORDER_CANDIDATE_AUDIT -> PAPER_ORDER_HANDOFF_DRY_RUN -> PAPER_SUPERVISED_ORDER_EXECUTION`

The patch does not force trades. It only submits a real paper order when every guarded and operator-controlled interlock is true.

## Safety constraints

Unchanged:

- no live execution
- no testnet execution
- no real exchange broker
- no automatic activation
- no legacy `ScoreOnly+Meta_OK` execution
- no threshold/risk/gate relaxation
- no order unless candidate/handoff/operator controls all pass

The legacy path remains blocked by `29.4.4r-1` and can still only emit `LEGACY_PAPER_ORDER_BLOCKED`.

## New files

- `trading_bot/core/paper_unlock_supervised_execution.py`
- `trading_bot/run_paper_unlock_supervised_execution.py`
- `trading_bot/test_paper_unlock_supervised_execution.py`

## Modified files

- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/core/paper_unlock_observation.py`
- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/run_paper_unlock_4h_observation.py`
- `trading_bot/run_paper_unlock_8h_observation.py`

## Runtime behavior

By default the feature is visible/reportable but operator execution is not active:

- `PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED=1`
- `PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE=0`
- `PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM=` empty

A real paper order can only be submitted if all are true:

- mode is paper
- candidate audit has `candidate_ready=true`
- handoff dry-run has `would_create_order=true`
- `paper_orders_enabled=true`
- `paper_unlock_experiment_allowed=true`
- `manual_activation_allowed=true`
- operator explicitly enables supervised execution
- operator confirmation equals `I_UNDERSTAND_PAPER_ONLY`
- live/testnet/exchange broker remain false
- open positions are below max positions

## New event

`PAPER_SUPERVISED_ORDER_EXECUTION`

Important fields:

- `supervised_submit_allowed`
- `operator_enable`
- `operator_confirmation_ok`
- `broker_submit_called`
- `orders_submitted_by_supervised`
- `positions_opened_by_supervised`
- `blocked_reasons`
- `live_allowed=false`
- `testnet_allowed=false`
- `exchange_broker_allowed=false`

## New report

`data/paper_unlock_supervised_execution_report.json`

Runner:

```cmd
python trading_bot\run_paper_unlock_supervised_execution.py
```

## Operator command for future supervised paper execution

Only after review and only when the guarded path actually produces a candidate-ready handoff:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock --paper-unlock-supervised-execution --paper-unlock-supervised-confirm I_UNDERSTAND_PAPER_ONLY
```

The command still cannot enable live/testnet/exchange broker.

## Validation

Sandbox validation passed:

```cmd
python trading_bot\test_paper_unlock_supervised_execution.py
python trading_bot\test_paper_order_leakage_guard.py
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
python trading_bot\test_paper_legacy_position_quarantine.py
python -m compileall -q trading_bot
```

The sandbox could not run `run_paper_trading.py` end-to-end because `ccxt` is not installed there. Local validation should run the once-cycle and reports.
