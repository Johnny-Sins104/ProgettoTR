# PROMPT 29.4.4s-10aw — LSR-v2 Visual SL/TP Progress Bar

## Scope

Extends the LSR-v2 Telegram trade dashboard with a visual SL/TP progress bar and price-distance diagnostics.

## Files

- `trading_bot/core/lsr_v2_telegram_trade_dashboard.py`
- `trading_bot/run_lsr_v2_telegram_trade_dashboard.py`
- `trading_bot/tests/test_lsr_v2_telegram_trade_dashboard.py`

## Behaviour

The dashboard remains a single-message Telegram-ready payload, but now includes:

- a visual progress bar in the form `SL =====●===== TP`;
- current-price marker position between SL and TP;
- distance from current price to TP;
- distance from current price to SL;
- SL/TP range progress percentage;
- entry-to-TP progress percentage;
- progress state (`IN_RANGE`, `TP_HIT_OR_BEYOND`, `SL_HIT_OR_BEYOND`, or `INSUFFICIENT_PRICE_DATA`).

The implementation supports both BUY and SELL directionality. Marker position is clamped for display while raw diagnostic percentages remain available in the report.

## Output additions

The generated dashboard report includes:

- `visual_sl_tp_progress_bar_ready`;
- `visual_sl_tp_progress_bar`;
- `visual_sl_tp_progress_pct`;
- `entry_to_tp_progress_pct`;
- `distance_to_take_profit`;
- `distance_to_stop_loss`;
- `progress_state`;
- `dashboard_cards.visual_sl_tp_progress`.

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

## Expected visual fields

- `visual_sl_tp_progress_bar_ready=true`
- `visual_sl_tp_progress_bar` contains `SL`, `●`, and `TP`
- `telegram_network_called=false`
- `telegram_send_allowed=false`

## Next patch

`29.4.4s-10ax — Trade Lifecycle Auto Monitoring`
