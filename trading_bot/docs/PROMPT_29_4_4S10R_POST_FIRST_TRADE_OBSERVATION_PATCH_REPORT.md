# PROMPT 29.4.4s-10r — LSR-v2 post-first-trade observation / no-reentry stability monitor

## Scope
Adds a read-only observation monitor after the first supervised LSR-v2 paper-only trade has completed and postmortem has passed.

## Added files
- `trading_bot/core/lsr_v2_post_first_trade_observation.py`
- `trading_bot/run_lsr_v2_post_first_trade_observation.py`
- `trading_bot/tests/test_lsr_v2_post_first_trade_observation.py`
- `trading_bot/docs/PROMPT_29_4_4S10R_POST_FIRST_TRADE_OBSERVATION_PATCH_REPORT.md`

## Outputs
- `data/lsr_v2_post_first_trade_observation_report.json`
- `data/lsr_v2_post_first_trade_observation.jsonl`
- `data/lsr_v2_post_first_trade_observation_logs/` when `--run-paper-cycles` is used

## Decisions
- `LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS`
- `KEEP_DIAGNOSTIC_LSR_V2_OBSERVATION_IN_PROGRESS`
- `KEEP_DIAGNOSTIC_LSR_V2_REENTRY_DETECTED`
- `KEEP_DIAGNOSTIC_LSR_V2_NEW_SUBMIT_DETECTED`
- `KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT`
- `REJECT_LSR_V2_POST_TRADE_OBSERVATION_FAILED`

## Safety invariants
- No new order.
- No new position.
- No close.
- No broker submit.
- No broker close.
- No paper state mutation.
- No paper status mutation.
- No re-entry.
- No live/testnet/exchange broker.

## Observation-loop safety
When `--run-paper-cycles` is used, the runner launches `run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock` with LSR-v2 submit/close/operator environment variables scrubbed from the subprocess environment.
