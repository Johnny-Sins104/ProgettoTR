ProgettoTR patch-only 29.4.4o-3c
====================================

Scope: console/output-only hardening for --once runs.

Install:
1. Extract this ZIP into C:\Users\Davide\Desktop\ProgettoTR-main
2. Accept overwrite.

Files included:
- trading_bot/run_paper_trading.py
- trading_bot/core/paper_once_console_summary.py
- trading_bot/core/paper_once_runner_footer.py
- docs/patch_reports/PROMPT_29_4_4O3C_PATCH_REPORT.md
- trading_bot/docs/patch_reports/PROMPT_29_4_4O3C_PATCH_REPORT.md

Why:
The cycle is completed and audit/bridge PASS, but python can remain alive after the last asset evaluation before the footer reaches stdout. This patch starts a --once watchdog outside the asyncio loop. After CYCLE_COMPLETED is written, it prints the runner fallback footer and exits the one-shot process.

Test:
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
type console_once_test.txt
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"[PAPER ONCE EXIT]" console_once_test.txt
findstr /n /C:"[PAPER ONCE RESULT]" console_once_test.txt

Safety unchanged: no live, no testnet, no exchange broker, no risk/gate/routing/order changes.
