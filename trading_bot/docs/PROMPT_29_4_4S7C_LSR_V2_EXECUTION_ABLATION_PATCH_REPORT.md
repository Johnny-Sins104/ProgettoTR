# Prompt 29.4.4s-7c — LSR-v2 execution/cost ablation audit

## Scope

Diagnostic-only patch that adds an execution/cost ablation layer above the validated LSR-v2 detector and backtest matrix.

The patch compares execution variants without changing runtime gates, risk thresholds, paper engine behavior, broker routing, or state files.

## Added files

- `trading_bot/core/lsr_v2_execution_ablation.py`
- `trading_bot/run_lsr_v2_execution_ablation.py`
- `trading_bot/tests/test_lsr_v2_execution_ablation.py`
- `trading_bot/docs/PROMPT_29_4_4S7C_LSR_V2_EXECUTION_ABLATION_PATCH_REPORT.md`

## Output artifacts

- `data/lsr_v2_execution_ablation_report.json`
- `data/lsr_v2_execution_ablation_variants.json`
- `data/lsr_v2_execution_ablation_trades.jsonl`
- `data/lsr_v2_cost_break_even_report.json`

## Variant grid

Entry policies:

- `retest_entry_limit_like`
- `retest_entry_mid`
- `retest_entry_close`
- `confirmation_close_entry`

Stop policies:

- `stop_at_sweep_extreme`
- `stop_at_sweep_extreme_plus_atr_buffer`

Target policies:

- `tp_fixed_1_5R`
- `tp_fixed_2R`
- `tp_structure_liquidity_target`

Max holding:

- `12`, `24`, `36` bars

Total default variants: 72.

## Decisions

Possible top-level decisions:

- `LSR_V2_EXECUTION_VARIANT_RESEARCH_READY`
- `KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE`
- `KEEP_DIAGNOSTIC_LSR_V2_COST_SENSITIVE`
- `REJECT_LSR_V2_CURRENT_EXECUTION`
- `KEEP_DIAGNOSTIC_LSR_V2_ABLATION_NO_TRADES`
- `KEEP_DIAGNOSTIC_NO_MARKET_DATA`
- `KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA`

## Safety

This patch is audit-only.

It does not:

- submit orders;
- open positions;
- mutate paper state;
- route signals;
- call brokers;
- enable live trading;
- enable testnet trading;
- enable exchange broker paths;
- lower thresholds;
- promote LSR-v2 to paper supervised.

`promotion_ready` remains `false` by design.

## Local validation commands

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_execution_ablation.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_execution_ablation.py --data-dir data --timeframe 5m
```

Recommended extended regression:

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_execution_ablation.py trading_bot\tests\test_lsr_v2_backtest_matrix.py trading_bot\tests\test_lsr_v2_trade_forensics.py trading_bot\tests\test_liquidity_sweep_reversal_v2.py
python -m compileall -q trading_bot
```
