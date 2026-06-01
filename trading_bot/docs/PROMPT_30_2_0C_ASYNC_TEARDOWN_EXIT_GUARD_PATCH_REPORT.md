# Prompt 30.2.0C - Async teardown exit guard

## Scope

This patch removes the unconditional final `os._exit(...)` path from the paper
runner after `asyncio.run(...)` returns and the engine has completed its normal
finalization.

The final process exit now goes through `_exit_process(...)`, which defaults to
`SystemExit(code)`.

## Why

`run_paper_trading.py --once` already has explicit engine finalization and the
paper engine closes its Telegram/background resources during teardown. A hard
process exit after that point can mask cleanup regressions and skip normal
Python shutdown behavior.

## Compatibility

The cycle-completed watchdog still uses `os._exit(0)` when a completed one-shot
cycle is detected and the engine remains stuck past the grace window.

The old final hard-exit behavior is still available by setting:

```text
PAPER_ONCE_FORCE_OS_EXIT=1
```

## Safety contract

- No broker calls.
- No order submit or close.
- No paper/live mode enablement change.
- No risk, signal, routing, or portfolio mutation.
- Watchdog hard exit remains restricted to completed-cycle hang recovery.

## Local validation

- `python -m py_compile trading_bot\run_paper_trading.py trading_bot\test_runtime_risk_io_hardening.py` -> PASS.
- `python trading_bot\test_runtime_risk_io_hardening.py` -> PASS.
- `python tools\run_checks.py --no-pytest` -> PASS: 657 Python files parsed, 0 syntax errors.
- Manual LSR-v2/paper regression runner -> PASS: 147 files loaded, 837 tests passed, 0 failed, 0 skipped, 0 import failures.

## Known environment gap

The bundled local Python does not currently have the full project dependency
set installed (`pytest`, `pytest_asyncio`, `aiohttp`, `ccxt`, `pandas_ta`,
`polars`, `pyarrow`, `requests`, `sklearn`, `xgboost`). The validation above
therefore uses the local no-pytest check runner plus a fixture-aware manual
regression runner.
