# PROMPT 29.4.4s-10af — LSR-v2 two-trade postmortem observation / third-trade lock monitor

## Scope

Adds a read-only observation layer after two supervised paper-only LSR-v2 trades have been opened, closed, and postmortem-audited. The patch verifies that the third trade remains locked, no re-entry or new submit appears, and `paper_state.json` / `paper_status.json` remain free of residual exposure.

## Files

- `trading_bot/core/lsr_v2_two_trade_observation.py`
- `trading_bot/run_lsr_v2_two_trade_observation.py`
- `trading_bot/tests/test_lsr_v2_two_trade_observation.py`

## Outputs

- `data/lsr_v2_two_trade_observation_report.json`
- `data/lsr_v2_two_trade_observation.jsonl`
- `data/lsr_v2_two_trade_observation_logs/`

## Decisions

- `LSR_V2_TWO_TRADE_OBSERVATION_PASS`
- `KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_OBSERVATION_IN_PROGRESS`
- `KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_OR_REENTRY_DETECTED`
- `KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_STATE_INCONSISTENT`
- `REJECT_LSR_V2_TWO_TRADE_OBSERVATION_FAILED`

## Safety

The patch never submits orders, opens positions, closes positions, mutates paper state/status, enables live/testnet/exchange broker, or allows re-entry. When running paper cycles, LSR-v2 manual route/submit/close/rearm environment variables are removed from the subprocess environment.
