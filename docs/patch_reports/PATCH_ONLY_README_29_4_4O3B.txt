ProgettoTR — Patch-only 29.4.4o-3b
====================================

Scope:
- Completa il footer --once con positions_opened_by_bridge.
- Aggiunge log console flush-only per fetch/evaluation:
  [FETCH START], [FETCH DONE], [FETCH ERROR], [EVALUATE START], [EVALUATE DONE].

Installazione:
1. Estrarre questo ZIP dentro C:\Users\Davide\Desktop\ProgettoTR-main
2. Accettare la sovrascrittura dei file.

Validazione consigliata:
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot

Test operativo:
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
type console_once_test.txt
findstr /n /C:"[FETCH START]" console_once_test.txt
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"positions_opened_by_bridge=0" console_once_test.txt
findstr /n /C:"[PAPER ONCE RESULT]" console_once_test.txt
python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py

Sicurezza invariata:
NO live, NO testnet, NO exchange broker reale, NO automatic activation, NO risk/gate/routing/broker changes, NO forced trades.
