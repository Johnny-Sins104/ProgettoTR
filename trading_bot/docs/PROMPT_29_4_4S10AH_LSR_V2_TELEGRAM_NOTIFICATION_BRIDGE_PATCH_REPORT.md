# Prompt 29.4.4s-10ah — LSR-v2 Telegram notification bridge

## Scope

Adds a read-only Telegram notification bridge for supervised LSR-v2 paper-trade artifacts.

The bridge reads existing reports and emits/audits notification messages for:

- second supervised paper order execution;
- second supervised paper position close;
- second closed-trade final audit;
- two-trade postmortem;
- two-trade observation.

## Files

- `trading_bot/core/lsr_v2_telegram_notification_bridge.py`
- `trading_bot/run_lsr_v2_telegram_notification_bridge.py`
- `trading_bot/tests/test_lsr_v2_telegram_notification_bridge.py`
- `trading_bot/docs/PROMPT_29_4_4S10AH_LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_PATCH_REPORT.md`

## Safety

The bridge is observability-only:

- no order submission;
- no position opening;
- no close execution;
- no broker submit/close calls;
- no `paper_state.json` mutation;
- no `paper_status.json` mutation;
- no live/testnet/exchange broker path;
- no re-entry.

Telegram send is disabled by default. Real send requires:

- `LSR_V2_TELEGRAM_BRIDGE_ENABLE=1`
- `LSR_V2_TELEGRAM_BRIDGE_CONFIRMATION=I_UNDERSTAND_SEND_LSR_V2_TELEGRAM_NOTIFICATIONS`
- valid `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.

## Outputs

- `data/lsr_v2_telegram_notification_bridge_report.json`
- `data/lsr_v2_telegram_notification_bridge.jsonl`
- `data/lsr_v2_telegram_notification_bridge_state.json`
- appends audit rows to `data/telegram_audit.jsonl`

## Validation

Sandbox validation:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_telegram_notification_bridge.py
6 passed

python -m compileall -q trading_bot
python -m py_compile trading_bot/core/lsr_v2_telegram_notification_bridge.py trading_bot/run_lsr_v2_telegram_notification_bridge.py
OK
```
