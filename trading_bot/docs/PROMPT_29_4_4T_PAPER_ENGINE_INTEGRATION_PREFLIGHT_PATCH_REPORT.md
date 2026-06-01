# PROMPT 29.4.4t — LSR-v2 Paper Engine integration planning / runner consolidation preflight

## Scope

Audit-only preflight for the architectural phase that will gradually consolidate the isolated LSR-v2 runners into the main paper engine path.

This patch does not integrate runtime hooks yet. It inspects the validated three-trade LSR-v2 state and maps the next integration points in:

- `trading_bot/core/paper_engine.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/avvia_bot_live.py`

## Added files

- `trading_bot/core/lsr_v2_paper_engine_integration_preflight.py`
- `trading_bot/run_lsr_v2_paper_engine_integration_preflight.py`
- `trading_bot/tests/test_lsr_v2_paper_engine_integration_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4T_PAPER_ENGINE_INTEGRATION_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4T_MANIFEST.txt`

## Inputs

- `data/lsr_v2_trade_lifecycle_auto_monitor_report.json`
- `data/lsr_v2_telegram_trade_dashboard_report.json`
- `data/lsr_v2_three_trade_postmortem_stability_lock_report.json`
- `data/paper_state.json`
- `data/paper_status.json`
- source files targeted for future integration

## Expected validated state

- `LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY`
- `LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY`
- `LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY`
- `fourth_trade_locked=true`
- `stability_lock_active=true`
- `open_positions_after=0`
- `paper_status_pending_orders_after=0`
- no active LSR-v2 operator env variables

## Output

- `data/lsr_v2_paper_engine_integration_preflight_report.json`
- `data/lsr_v2_paper_engine_integration_preflight.jsonl`

Expected decision:

```text
LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY
```

## Safety contract

This patch is planning-only and audit-only:

- no paper order submission
- no position opening
- no position closing
- no broker call
- no Telegram network send
- no scheduler start
- no paper_state mutation
- no paper_status mutation
- no fourth trade or re-entry
- no live/testnet/exchange broker

## Next patch

`29.4.4t-1 — Engine read-only dashboard/lifecycle artifact hook`

The next patch should still be read-only and should add a guarded artifact hook to the paper engine finalization path without changing routing, broker, order, position, or Telegram-send behavior.
