# Prompt 30.0.0A - Working tree normalization

## Scope

This patch starts the repository normalization phase from the roadmap.
It does not try to stage, commit, delete, or move the existing patch files.
Instead it makes the current state auditable before the next real commit.

## Added

- `tools/working_tree_audit.py`
- `docs/patch_reports/PATCH_30_0_0A_MANIFEST.txt`

## Changed

- `.gitignore` now ignores local pytest cache, `trading_bot/scratch/`,
  `console_once*.txt`, and `patch_reports.zip`.

## Classification policy

The audit tool separates the working tree into buckets:

- tracked modified files
- tracked deleted files
- untracked source Python
- untracked tests
- untracked patch documentation
- untracked generated archives
- untracked console output
- other untracked files

This keeps future staging decisions explicit. In particular, untracked LSR-v2
Python modules are treated as source, not as generated output.

## Safety contract

- No files are deleted.
- No files are moved.
- No files are staged or committed.
- No runtime data is mutated.
- No paper/live/testnet/exchange path is enabled.

## Local validation

- `python -m py_compile tools/working_tree_audit.py` -> PASS
- `python tools/working_tree_audit.py --limit 8` -> PASS
- `.gitignore` check for `patch_reports.zip`, `console_once*.txt`, `.pytest_cache/`, `trading_bot/.pytest_cache/`, `trading_bot/scratch/` -> PASS

Current audit buckets after this patch:

- tracked deleted: 7
- tracked modified: 29
- untracked patch documentation: 335
- untracked project documentation: 1
- untracked source Python: 309
- untracked tests: 154
- untracked tooling: 1

## Next step

Use the audit output to create small commit sets:

1. normalization docs and tooling;
2. tested source patch files;
3. tests;
4. patch reports that should remain historical documentation;
5. leave generated outputs ignored or unstaged.
