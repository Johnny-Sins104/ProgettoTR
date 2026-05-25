PATCH ONLY — ProgettoTR 29.4.4r
=================================

Patch: 29.4.4r — Paper order submission dry-run / simulated broker handoff

Installazione:
1. Estrarre questo ZIP sopra C:\Users\Davide\Desktop\ProgettoTR-main
2. Accettare la sovrascrittura dei file.

Comandi consigliati:

cd C:\Users\Davide\Desktop\ProgettoTR-main

python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py

python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1

type console_once_test.txt
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"[PAPER ONCE EXIT]" console_once_test.txt

python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
python trading_bot\run_paper_unlock_candidate_audit.py
python trading_bot\run_paper_unlock_handoff_dry_run.py

Sicurezza:
- No live
- No testnet
- No exchange broker reale
- No order submission
- No position opening
- No gate/risk/signal/routing changes
- Handoff is dry-run only
