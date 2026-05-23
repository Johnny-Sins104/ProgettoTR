# Prompt 29.4.4a — Unlock rejection analysis + range-position shadow review

## Scope

This patch adds a diagnostic-only unlock rejection report for the Prompt 29.4.4 paper unlock gate. It explains why the runtime emits `PAPER_UNLOCK_EVALUATED` rows but does not necessarily emit `PAPER_UNLOCK_SIGNAL` rows.

## Safety

- No live execution enabled.
- No testnet execution enabled.
- No paper trades are forced.
- No strategy threshold is changed.
- No risk setting is changed.
- `RANGE_POSITION_FILTERED` remains operationally blocked.
- The report reads only `data/paper_events.jsonl` and writes JSON reports.

## New file

```text
trading_bot/core/paper_unlock_rejection_analysis.py
```

Writes:

```text
data/paper_unlock_rejection_report.json
```

## Modified files

```text
trading_bot/config.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/run_paper_trading.py
.env.example
docs/patch_reports/PROMPT_29_4_4A_PATCH_REPORT.md
```

## Report contents

The new report includes:

- total `PAPER_UNLOCK_EVALUATED` rows;
- accepted/rejected unlock rows;
- BTC-only counts;
- reason distribution;
- per-asset rejection tables;
- `ai_prob`, `setup_quality`, `technical_score` distributions;
- near-threshold candidate count;
- dedicated `RANGE_POSITION_FILTERED` review;
- deterministic recommendation for the next patch.

## Runtime integration

The report is generated together with the existing paper performance artifacts. The status file now includes:

```text
paper_unlock_rejection_report_path
paper_unlock_rejection_analysis
unlock_rejection_analysis_enabled
```

The performance report now includes:

```text
unlock_rejection_analysis
signals.unlock_rejection_status
signals.unlock_rejection_decision
signals.unlock_rejection_dominant_btc_reason
```

The dashboard now has an `Unlock Rejection Analysis` card.

## CLI

Optional disable flag:

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --no-unlock-rejection-analysis
```

Default remains enabled:

```env
PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED=1
```

## Smoke result on provided runtime artifacts

Using the uploaded runtime files:

```text
paper_unlock_evaluated: 192
paper_unlock_accepted_evaluations: 0
btc_evaluated: 48
btc_rejected: 48
near_threshold_candidates: 2
btc_near_threshold_candidates: 0
```

Dominant decision:

```text
NO_DIRECTION_DOMINANT
```

BTC dominant reason:

```text
no_intended_side
```

Range-position section:

```text
range_position_review.evaluated: 27
range_position_review.recommendation: KEEP_BLOCKED
```

Interpretation: do not relax gates. The next structural patch should improve scenario/side attribution, likely `29.5.0a — Crypto intraday scenario engine`, before continuing paper expansion.

## Validation

```text
py_compile OK:
- trading_bot/config.py
- trading_bot/run_paper_trading.py
- trading_bot/core/paper_unlock_rejection_analysis.py
- trading_bot/core/paper_performance.py
- trading_bot/core/paper_engine.py

Report generation OK on supplied data.
Performance artifact integration OK.
Full paper runtime not executed in sandbox because ccxt is not installed here.
```
