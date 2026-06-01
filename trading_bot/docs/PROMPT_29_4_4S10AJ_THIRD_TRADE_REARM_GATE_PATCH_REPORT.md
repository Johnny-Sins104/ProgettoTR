# Prompt 29.4.4s-10aj — LSR-v2 third paper trade rearm gate

## Scope

Adds a diagnostic-only/manual rearm gate for the third supervised LSR-v2 paper trade after:

- two-trade paper-cycle postmortem PASS;
- post-two-trade observation PASS, including 4h/8h thresholds;
- Telegram event bridge and position monitor readiness;
- no residual position, no pending orders, no re-entry and third trade still locked.

## New files

- `trading_bot/core/lsr_v2_third_trade_rearm_gate.py`
- `trading_bot/run_lsr_v2_third_trade_rearm_gate.py`
- `trading_bot/tests/test_lsr_v2_third_trade_rearm_gate.py`

## Outputs

- `data/lsr_v2_third_trade_rearm_gate_report.json`
- `data/lsr_v2_third_trade_rearm_gate.jsonl`

## Operator controls

The rearm gate is disabled by default. Manual rearm requires:

```powershell
$env:LSR_V2_THIRD_TRADE_REARM_ENABLE="1"
$env:LSR_V2_THIRD_TRADE_REARM_CONFIRMATION="I_UNDERSTAND_THIRD_PAPER_TRADE_DIAGNOSTIC_ONLY"
$env:LSR_V2_THIRD_TRADE_MAX_ORDERS="1"
```

Expected armed decision:

```text
LSR_V2_THIRD_TRADE_REARM_READY_DIAGNOSTIC
```

## Safety invariants

This patch never:

- submits orders;
- opens positions;
- closes positions;
- calls a broker submit/close method;
- mutates `paper_state.json`;
- mutates `paper_status.json`;
- enables live/testnet/exchange broker;
- enables operational unlock;
- enables third-trade submit/execution.

## Validation

Sandbox validation:

```text
python -m pytest -q trading_bot/tests/test_lsr_v2_third_trade_rearm_gate.py
7 passed

python -m compileall -q trading_bot
OK
```
