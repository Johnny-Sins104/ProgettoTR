# Prompt 30.3.0L - LSR-v2 paper submit anti-stale guard

## Objective

Prevent paper-live execution from opening trades on LSR-v2 candidates that were
detected many candles before the current market candle.

## Behavior

The runtime bridge now emits:

- `candidate_age_bars`
- `max_submit_candidate_age_bars`
- `candidate_fresh_for_submit`
- `runtime_candidate_fresh_for_submit`

If a candidate is ready but stale, it remains visible in diagnostics with
`runtime_candidate_stale_for_submit`, but `PaperTradingEngine` will not call the
paper broker submit path.

## Default

`max_submit_candidate_age_bars=3`.

On 5m candles this means a candidate must be no more than roughly 15 minutes old
to be eligible for a supervised paper submit.

## Validation

- Compile check passed for `lsr_v2_runtime_bridge.py` and `paper_engine.py`.
- Manual smoke passed for:
  - recent candidate audit;
  - stale candidate blocked with `runtime_candidate_stale_for_submit`;
  - no-candidate audit.
- `pytest` was not available in the current Python interpreter, so the pytest
  suite should be rerun once the test dependency is present.
