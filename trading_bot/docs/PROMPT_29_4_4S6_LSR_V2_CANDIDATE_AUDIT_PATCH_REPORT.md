# Prompt 29.4.4s-6 — LSR-v2 audit-only candidate detector

## Scope

This patch adds a diagnostic-only detector for `LIQUIDITY_SWEEP_REVERSAL_V2`.
It is designed to identify candidate events for later backtest matrix and cost
stress validation. It does not route, submit, create paper orders, open
positions, call a broker, enable live/testnet, or modify runtime strategy gates.

## Candidate model

The detector audits this sequence:

```text
liquidity pool -> sweep -> failed continuation -> reclaim -> CHoCH/BOS approximation -> retest candidate
```

A candidate can be emitted before execution eligibility. `candidate_ready=true`
requires risk/reward, cost-to-R and, by default, retest readiness. This flag is
still audit-only and must not be interpreted as permission to submit an order.

## Added files

```text
trading_bot/core/liquidity_sweep_reversal_v2.py
trading_bot/run_lsr_v2_candidate_audit.py
trading_bot/tests/test_liquidity_sweep_reversal_v2.py
trading_bot/docs/PROMPT_29_4_4S6_LSR_V2_CANDIDATE_AUDIT_PATCH_REPORT.md
PATCH_29_4_4S6_MANIFEST.txt
```

## Output artifacts

```text
data/lsr_v2_candidate_audit.jsonl
data/lsr_v2_candidate_audit_report.json
```

## Decisions

```text
LSR_V2_CANDIDATE_AUDIT_READY_DIAGNOSTIC
KEEP_DIAGNOSTIC_NO_MARKET_DATA
KEEP_DIAGNOSTIC_MARKET_DATA_LOAD_ERROR
```

## Safety invariants

```text
orders_submitted_by_lsr_v2 = 0
positions_opened_by_lsr_v2 = 0
live_allowed = false
testnet_allowed = false
exchange_broker_allowed = false
audit_only = true
promotion_ready = false
```

## Local validation commands

```powershell
python -m pytest -q trading_bot\tests\test_liquidity_sweep_reversal_v2.py
python -m compileall -q trading_bot
python trading_bot\run_lsr_v2_candidate_audit.py --data-dir data --timeframe 5m
```

## Expected next patch

`29.4.4s-7 — LSR-v2 backtest matrix / cost stress grid` should consume the
JSONL audit output and validate candidates across 10k/12k/15k/18k/20k/30k/50k
windows with conservative and severe cost assumptions.
