# PROMPT 29.4.4r-1 PATCH REPORT — Legacy paper order leakage audit + fail-closed paper submission guard

## Scope

Patch 29.4.4r-1 blocks the legacy paper execution path discovered during the 29.4.4r-OBS dry-run observation. The 8h observation showed that the guarded layers did not submit orders, but the older `ScoreOnly+Meta_OK` paper path still emitted paper orders and positions.

This patch is safety-only and diagnostic-only:

- no live mode
- no testnet mode
- no exchange broker
- no risk increase
- no gate/threshold/signal/routing changes
- no broker handoff activation
- no supervised paper execution activation

## Added files

- `trading_bot/core/paper_order_leakage_guard.py`
- `trading_bot/run_paper_order_leakage_guard.py`
- `trading_bot/test_paper_order_leakage_guard.py`

## Modified files

- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_unlock_observation.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/run_paper_unlock_4h_observation.py`
- `trading_bot/run_paper_unlock_8h_observation.py`
- `trading_bot/config.py`

## Runtime behavior

When the legacy engine produces a BUY/SELL signal, the paper engine now performs a fail-closed guard before calling `PaperBrokerAdapter.place_order()`.

During this phase, the allowed order source is:

```text
allowed_order_source = NONE
```

A legacy signal can be recorded diagnostically, but it cannot become:

- `PAPER_ORDER_SUBMITTED`
- `ORDER_FILLED`
- `PAPER_ORDER_CONFIRMED`
- `POSITION_OPENED`

Instead, it emits:

```text
LEGACY_PAPER_ORDER_BLOCKED
```

The blocked event records symbol, side, entry, stop, target, qty, notional, risk amount, original score/metadata, and `blocked_reason=paper_order_source_not_authorized`.

## Report

New report:

```text
data/paper_order_leakage_guard_report.json
```

New runner:

```cmd
python trading_bot\run_paper_order_leakage_guard.py
```

The report detects historical and current unauthorized paper orders/positions from `paper_events.jsonl`, including legacy `ScoreOnly+Meta_OK` orders.

## Observation report integration

The 4h/8h observation reports now include leakage metrics:

- `legacy_order_leakage_detected`
- `unauthorized_orders_count`
- `unauthorized_positions_opened_count`
- `blocked_legacy_order_attempts`

Safety checks now fail if unauthorized orders or positions are present.

## Config

New config/env controls:

```text
PAPER_ORDER_LEAKAGE_GUARD_ENABLED=1
PAPER_ORDER_LEAKAGE_GUARD_FAIL_CLOSED=1
PAPER_ORDER_LEAKAGE_GUARD_ALLOW_SUPERVISED=0
PAPER_ORDER_LEAKAGE_GUARD_ALLOWED_SOURCE=NONE
PAPER_ORDER_LEAKAGE_GUARD_REPORT_NAME=paper_order_leakage_guard_report.json
```

## Current-data diagnostic result

On the uploaded project data, the leakage report correctly returns WARN/KEEP_DIAGNOSTIC because historical legacy paper orders already exist:

```text
legacy_order_leakage_detected=true
unauthorized_orders_count=3
unauthorized_positions_opened_count=3
cycle_orders_total=3
max_open_positions=2
allowed_order_source=NONE
fail_closed=true
```

This is expected and confirms that the patch can identify the previously observed leakage.

## Tests executed

```cmd
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
python -m compileall -q trading_bot
```

All passed in sandbox.

## Post-install validation

Run:

```cmd
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\run_paper_order_leakage_guard.py
```

Then run a new once-cycle:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
```

Expected behavior if a legacy signal appears:

```text
[PAPER ORDER BLOCKED] symbol=... side=... reason=paper_order_source_not_authorized source=legacy_score_meta
```

and no new `PAPER_ORDER_FILLED` or `PAPER_POSITION_OPENED` should be produced.
