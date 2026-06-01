# Prompt 30.2.0A - JSONL tail reader everywhere

## Scope

This patch replaces local JSONL tail helpers that loaded full files into memory
with wrappers around `core.jsonl_utils.iter_jsonl_tail`.

It targets helper functions named:

- `_iter_jsonl_tail`
- `_iter_jsonl_events`
- `_iter_jsonl`

Full-file readers used for deliberate trade/backtest dataset analysis are left
unchanged.

## Why

Long-running `paper_events.jsonl` and LSR-v2 audit logs can become large. Tail
helpers should not call `read_text().splitlines()` because that loads the whole
file before keeping only the last rows.

## Safety contract

- Diagnostic/read-only behavior only.
- No state mutation.
- No broker/network calls.
- No order submit or close.
- No live/testnet/exchange behavior enabled.

## Local validation

- AST parse for `trading_bot/core/*.py` -> PASS, 248 files checked, 0 errors.
- `python tools\run_checks.py --no-pytest` -> PASS, 657 Python files parsed, 0 syntax errors.
- Manual LSR-v2/paper regression runner -> PASS: 147 test files loaded, 835 tests passed, 0 failed, 0 import failures.
- Regression source scan -> PASS: no local `_iter_jsonl_tail`, `_iter_jsonl_events`, or `_iter_jsonl` helper still uses `read_text().splitlines()`.

## Notes

`paper_once_runner_footer.py` now uses the shared tail reader too. It still
returns an iterable/list to preserve caller behavior.
