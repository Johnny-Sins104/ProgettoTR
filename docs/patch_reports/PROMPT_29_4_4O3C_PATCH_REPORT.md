# Prompt 29.4.4o-3c — Paper once post-cycle watchdog / hard one-shot exit

## Scope

Console/output-only hotfix on top of 29.4.4o-3b.

The user observed that `run_paper_trading.py --once` writes a valid `CYCLE_COMPLETED` event and the audit/bridge runners read the new cycle successfully, but the Python process remains alive after the last asset evaluation and the paper once footer is not emitted to stdout.

## Cause addressed

The engine can remain stuck in post-cycle finalization or shutdown after `CYCLE_COMPLETED` is already present in `data/paper_events.jsonl`. A fallback inside the engine or inside the normal runner `finally` is not enough when the event loop or shutdown path does not return.

## Implementation

`trading_bot/run_paper_trading.py` now starts a daemon watchdog thread only for `--once` runs. The watchdog:

- polls `data/paper_events.jsonl` from outside the asyncio event loop;
- detects the latest `CYCLE_COMPLETED` generated after command start;
- waits a short grace window;
- prints the runner fallback footer using `print_runner_once_footer_from_events()` if the engine did not already print it;
- prints `[PAPER ONCE EXIT]`;
- terminates the one-shot process with `os._exit(0)`.

Environment controls:

```text
PAPER_ONCE_HARD_EXIT_AFTER_COMPLETED=1/0   default 1
PAPER_ONCE_HARD_EXIT_GRACE_SECONDS=3.0     default 3.0
PAPER_ONCE_WATCHDOG_POLL_SECONDS=0.25      default 0.25
PAPER_ONCE_WATCHDOG_TIMEOUT_SECONDS=300    default 300
```

Footer prompt markers are updated to `29.4.4o-3c`.

## Files changed

```text
trading_bot/run_paper_trading.py
trading_bot/core/paper_once_console_summary.py
trading_bot/core/paper_once_runner_footer.py
docs/patch_reports/PROMPT_29_4_4O3C_PATCH_REPORT.md
trading_bot/docs/patch_reports/PROMPT_29_4_4O3C_PATCH_REPORT.md
PATCH_ONLY_README_29_4_4O3C.txt
```

## Safety

No trading logic is changed.

```text
NO gate changes
NO risk changes
NO signal logic changes
NO routing changes
NO broker changes
NO live
NO testnet
NO exchange broker real enablement
NO automatic activation
NO order submission
NO position opening
```

The watchdog only acts after a completed cycle is already written to the event log and only for `--once` runs.

## Validation

Sandbox tests run:

```cmd
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```
