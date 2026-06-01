# Prompt 30.1.0B - Portfolio risk current snapshot guard

## Scope

The current code already passes `portfolio_var` from `snapshot()` into
`_concentration_flags()`. This patch strengthens the regression test so the
guard cannot silently fall back to `self.snapshots[-1]` again.

## Added test coverage

- Seed an old snapshot with `portfolio_var=0`.
- Force the current snapshot calculation to return `portfolio_var=100`.
- Assert that the new snapshot contains `VAR_LIMIT_EXCEEDED`.

## Safety contract

- Test-only change.
- No state file writes.
- No broker/network/trading path calls.
- No live/testnet/exchange behavior enabled.

## Expected result

`VAR_LIMIT_EXCEEDED` must be computed from the current tick, not the previous
snapshot history.

## Local validation

- `python trading_bot\test_runtime_risk_io_hardening.py` -> PASS
- `python tools\run_checks.py --no-pytest` -> PASS, 657 Python files parsed, 0 syntax errors
