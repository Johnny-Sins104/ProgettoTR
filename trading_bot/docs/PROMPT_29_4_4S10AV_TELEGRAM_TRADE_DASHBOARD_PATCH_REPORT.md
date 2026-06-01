# PROMPT 29.4.4s-10av — LSR-v2 Telegram Trade Dashboard

## Scope

Adds a dashboard-only, read-only Telegram-ready summary for the completed three-trade LSR-v2 paper cycle.

## Files

- `trading_bot/core/lsr_v2_telegram_trade_dashboard.py`
- `trading_bot/run_lsr_v2_telegram_trade_dashboard.py`
- `trading_bot/tests/test_lsr_v2_telegram_trade_dashboard.py`

## Behaviour

The dashboard reads existing three-trade postmortem, third trade close/preflight/final-audit, paper state and paper status artifacts. It builds one updateable Telegram message containing:

- three-trade status;
- balance and aggregate PnL;
- realized R;
- flat/pending status;
- fourth-trade lock status;
- last trade entry, current price, SL, TP, PnL and R multiple.

## Safety contract

This patch is dashboard-only:

- no order submission;
- no position opening;
- no position closing;
- no broker calls;
- no Telegram network send;
- no `paper_state.json` mutation;
- no `paper_status.json` mutation;
- no re-entry;
- no live/testnet/exchange broker.

## Expected PASS decision

`LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY`

## Next patch

`29.4.4s-10aw — Visual SL/TP Progress Bar`
