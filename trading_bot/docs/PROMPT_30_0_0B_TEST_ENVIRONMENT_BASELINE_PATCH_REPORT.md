# Prompt 30.0.0B - Test environment baseline

## Scope

This patch adds a repeatable test/check baseline after the working tree audit.
It does not install dependencies automatically and does not mutate runtime data.

## Added

- `trading_bot/requirements-dev.txt`
- `tools/run_checks.py`
- `docs/patch_reports/PATCH_30_0_0B_MANIFEST.txt`

## Check command

Before installing dev dependencies:

```powershell
& "C:\Users\Davide\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\run_checks.py --no-pytest
```

After installing dev dependencies:

```powershell
& "C:\Users\Davide\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r trading_bot\requirements-dev.txt
& "C:\Users\Davide\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\run_checks.py
```

## Dependency policy

`tools/run_checks.py` reports missing packages but only fails on them with
`--require-deps`. This lets syntax checks run on partial local environments.

## Smoke tests

When `pytest` is available, the runner executes a focused smoke set:

- `trading_bot/test_runtime_risk_io_hardening.py`
- `trading_bot/test_paper_unlock_supervised_inactive_observation.py`
- `trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py`
- `trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py`

## Safety contract

- No files in `data/` are written.
- No broker/network/runtime trading path is called.
- No paper/live/testnet/exchange behavior is enabled.

## Local validation

- `python -m py_compile tools/run_checks.py` -> PASS
- `python tools/run_checks.py --no-pytest` -> PASS
- Syntax parse: 656 Python files checked, 0 syntax errors.
- Missing dependencies reported in this local runtime: `aiohttp`, `ccxt`, `pandas_ta`, `polars`, `pyarrow`, `requests`, `sklearn`, `xgboost`, `pytest`, `pytest_asyncio`.
