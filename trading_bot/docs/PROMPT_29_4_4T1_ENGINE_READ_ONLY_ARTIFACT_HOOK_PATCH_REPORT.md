# PROMPT 29.4.4t-1 — LSR-v2 Engine Read-Only Dashboard/Lifecycle Artifact Hook

## Scope

This patch adds the first read-only connection between the main Paper Engine and the validated LSR-v2 dashboard/lifecycle artifact chain.

It does **not** consolidate isolated runners yet and does **not** enable runtime trading actions. The hook only reads already generated LSR-v2 reports, builds an engine-consumable snapshot, and writes a diagnostic report/JSONL for future runner/footer consolidation.

## Files

- `trading_bot/core/lsr_v2_engine_read_only_artifact_hook.py`
- `trading_bot/run_lsr_v2_engine_read_only_artifact_hook.py`
- `trading_bot/tests/test_lsr_v2_engine_read_only_artifact_hook.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/docs/PROMPT_29_4_4T1_ENGINE_READ_ONLY_ARTIFACT_HOOK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T1_MANIFEST.txt`

## Inputs

The hook reads:

- `data/lsr_v2_paper_engine_integration_preflight_report.json`
- `data/lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `data/lsr_v2_telegram_trade_dashboard_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- active `LSR_V2_*` operator environment variables

## Outputs

The hook writes only:

- `data/lsr_v2_engine_read_only_artifact_hook_report.json`
- `data/lsr_v2_engine_read_only_artifact_hook.jsonl`

Expected PASS decision:

```text
LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY
```

## Engine wiring

`PaperTradingEngine.write_performance_artifacts()` now calls the read-only hook and includes the result under:

```text
lsr_v2_engine_read_only_artifact_hook
```

This is still an artifact-only hook. It does not change order evaluation, routing, broker handoff, position lifecycle, Telegram sending, or scheduler behavior.

A CLI opt-out was added:

```text
--no-lsr-v2-engine-read-only-artifact-hook
```

## Safety contract

The patch guarantees:

- no order submission
- no position opening
- no position closing
- no broker call
- no paper state mutation
- no paper status mutation
- no re-entry
- no fourth trade
- no scheduler start
- no Telegram network call
- no Telegram send
- no live broker
- no testnet broker
- no exchange broker

## Validation

Sandbox validation passed:

```text
python -m compileall -q trading_bot
PYTHONPATH=.:trading_bot python -m pytest -q \
  trading_bot/tests/test_lsr_v2_engine_read_only_artifact_hook.py \
  trading_bot/tests/test_lsr_v2_paper_engine_integration_preflight.py \
  trading_bot/tests/test_lsr_v2_trade_lifecycle_auto_monitor.py \
  trading_bot/tests/test_lsr_v2_telegram_trade_dashboard.py \
  trading_bot/tests/test_lsr_v2_three_trade_postmortem_stability_lock.py \
  trading_bot/tests/test_lsr_v2_third_closed_trade_final_audit.py \
  trading_bot/tests/test_lsr_v2_third_trade_close_execution.py \
  trading_bot/tests/test_lsr_v2_third_trade_close_preflight.py \
  trading_bot/tests/test_lsr_v2_third_open_position_monitor.py \
  trading_bot/tests/test_lsr_v2_third_trade_submit_execution.py \
  trading_bot/test_paper_order_leakage_guard.py
```

## Next patch

Recommended next patch:

```text
29.4.4t-2 — Paper runner footer/console visibility consolidation
```

That patch may surface the read-only hook summary in the `--once` footer and operator console, still without trading actions.
