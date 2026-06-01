# Prompt 29.4.4s-7 — LSR-v2 backtest matrix / cost stress grid

## Scope

Diagnostic-only backtest layer for `LIQUIDITY_SWEEP_REVERSAL_V2`.

The patch converts `candidate_ready=true` LSR-v2 audit candidates into simulated trades across multiple history windows and cost scenarios. It is not an execution patch.

## Added files

```text
trading_bot/core/lsr_v2_backtest_matrix.py
trading_bot/run_lsr_v2_backtest_matrix.py
trading_bot/tests/test_lsr_v2_backtest_matrix.py
trading_bot/docs/PROMPT_29_4_4S7_LSR_V2_BACKTEST_MATRIX_PATCH_REPORT.md
PATCH_29_4_4S7_MANIFEST.txt
```

## Outputs

```text
data/lsr_v2_backtest_matrix_report.json
data/lsr_v2_cost_stress_report.json
data/lsr_v2_trades_10k.jsonl
data/lsr_v2_trades_12k.jsonl
data/lsr_v2_trades_15k.jsonl
data/lsr_v2_trades_18k.jsonl
data/lsr_v2_trades_20k.jsonl
data/lsr_v2_trades_30k.jsonl
data/lsr_v2_trades_50k.jsonl
```

Each trade file can contain rows for multiple cost models. Every row is marked `audit_only=true`, `submit_order=false`, `route_order=false`, and `broker_submit_called=false`.

## Simulation model

- Candidate detection reuses the s-6b LSR-v2 detector.
- Only `candidate_ready=true` candidates are simulated.
- Entry is the retest entry level from the candidate audit.
- Stop loss and take profit are the candidate levels.
- If SL and TP are touched in the same bar, the simulator chooses the stop loss conservatively.
- Default simulation is one-position-at-time; overlapping candidates are skipped.
- Costs are applied as post-entry/post-exit R drag using base, conservative and severe scenarios.

## Promotion policy

Even if the matrix is positive, `promotion_ready=false`. Promotion still requires walk-forward, embargoed out-of-sample, bootstrap, and the strategy promotion gate.

## Safety

No live, no testnet, no exchange broker, no broker call, no order submission, no position opening, no threshold lowering, no paper state mutation.

## Local validation commands

```powershell
python -m pytest -q trading_bot\tests\test_lsr_v2_backtest_matrix.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_backtest_matrix.py --data-dir data --timeframe 5m
```
