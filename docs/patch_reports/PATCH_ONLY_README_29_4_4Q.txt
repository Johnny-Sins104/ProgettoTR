ProgettoTR patch-only package: 29.4.4q — First guarded paper-order candidate audit

Install:
1. Extract this ZIP into C:\Users\Davide\Desktop\ProgettoTR-main
2. Accept overwrite.

This patch assumes the project already contains 29.4.4o-3c.

New command:
  python trading_bot\run_paper_unlock_candidate_audit.py

Validation:
  python trading_bot\test_paper_unlock_candidate_audit.py
  python trading_bot\test_paper_unlock_routing_bridge.py
  python trading_bot\test_paper_unlock_runtime_audit.py
  python trading_bot\test_paper_once_console_summary.py
  python trading_bot\test_paper_once_runner_footer.py
  python -m compileall -q trading_bot

Operational test:
  python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
  type console_once_test.txt
  findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
  python trading_bot\run_paper_unlock_runtime_audit.py
  python trading_bot\run_paper_unlock_routing_bridge.py
  python trading_bot\run_paper_unlock_candidate_audit.py

Safety unchanged:
- no live
- no testnet
- no exchange broker
- no automatic activation
- no order submission by candidate audit
- no position opening by candidate audit
