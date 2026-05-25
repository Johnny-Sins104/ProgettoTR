ProgettoTR patch-only package
Patch: 29.4.4s-OBS — Supervised inactive observation / candidate exposure monitor

Install by extracting this ZIP over the project root.

After extraction run:

cd C:\Users\Davide\Desktop\ProgettoTR-main

python trading_bot\test_paper_unlock_supervised_inactive_observation.py
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

Smoke test:

python trading_bot\run_paper_unlock_supervised_inactive_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1

Full 4h inactive observation:

python trading_bot\run_paper_unlock_supervised_inactive_observation.py --duration-hours 4 --interval-seconds 300

Report:

data\paper_unlock_supervised_inactive_observation_report.json

Safety:
- no live
- no testnet
- no exchange broker
- no broker submit
- no order submission
- no position opening
- operator supervised execution remains inactive by default
