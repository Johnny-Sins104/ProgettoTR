# Prompt 29.4.4s-7b — LSR-v2 trade forensics / concentration and cost-failure attribution

## Scope

Diagnostic-only attribution layer for the LSR-v2 backtest matrix produced by Prompt 29.4.4s-7.

The patch reads existing `data/lsr_v2_trades_*.jsonl`, `data/lsr_v2_backtest_matrix_report.json`, and `data/lsr_v2_cost_stress_report.json` files. It does not regenerate candidates, does not route signals, does not call any broker, and does not mutate paper state.

## New files

- `trading_bot/core/lsr_v2_trade_forensics.py`
- `trading_bot/run_lsr_v2_trade_forensics.py`
- `trading_bot/tests/test_lsr_v2_trade_forensics.py`
- `trading_bot/docs/PROMPT_29_4_4S7B_LSR_V2_TRADE_FORENSICS_PATCH_REPORT.md`

## Reports

- `data/lsr_v2_trade_forensics_report.json`
- `data/lsr_v2_trade_forensics_by_window.json`
- `data/lsr_v2_cost_failure_attribution_report.json`

## Decisions

- `LSR_V2_FORENSICS_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE`
- `KEEP_DIAGNOSTIC_LSR_V2_FORENSICS_NO_TRADES`
- `KEEP_DIAGNOSTIC_LSR_V2_FORENSICS_ERROR`

## Classification labels

- `FRAGILE_POSITIVE_EDGE`
- `LOW_SAMPLE_EDGE`
- `OUTLIER_DOMINATED_EDGE`
- `COST_SENSITIVE_EDGE`
- `WINDOW_INSTABILITY_EDGE`
- `REJECT_LSR_V2_CURRENT_FORM`
- `RESEARCH_READY_FOR_WALK_FORWARD`

## Safety invariants

- No live trading.
- No testnet trading.
- No exchange broker.
- No broker submit.
- No order submission.
- No position opening.
- No paper-state mutation.
- `promotion_ready=false` by design.

## Local validation

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_trade_forensics.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_trade_forensics.py --data-dir data
```

Expected output on the current LSR-v2 run should remain diagnostic. If the previous `s-7` blockers are present, the expected decision is `KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE`.
