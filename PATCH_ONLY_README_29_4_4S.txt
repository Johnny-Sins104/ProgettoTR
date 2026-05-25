ProgettoTR patch-only package
Patch: 29.4.4s — First real paper-only order execution, supervised

Extract this ZIP over the project root.

Validation commands:

cd C:\Users\Davide\Desktop\ProgettoTR-main

python trading_bot\test_paper_unlock_supervised_execution.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python -m compileall -q trading_bot

Current diagnostic report:

python trading_bot\run_paper_unlock_supervised_execution.py

Normal once-cycle, still inactive unless candidate/handoff/operator controls pass:

python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1

type console_once_test.txt
python trading_bot\run_paper_order_leakage_guard.py
python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
python trading_bot\run_paper_unlock_candidate_audit.py
python trading_bot\run_paper_unlock_handoff_dry_run.py
python trading_bot\run_paper_unlock_supervised_execution.py

Future supervised paper-only command, only after candidate_ready/would_create_order appears and you choose to supervise it:

python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock --paper-unlock-supervised-execution --paper-unlock-supervised-confirm I_UNDERSTAND_PAPER_ONLY

Safety unchanged:
NO live
NO testnet
NO exchange broker
NO automatic activation
NO legacy ScoreOnly+Meta_OK execution
