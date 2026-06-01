PATCH ONLY — ProgettoTR 29.4.4r-1
===================================

Patch:
29.4.4r-1 — Legacy paper order leakage audit + fail-closed paper submission guard

Installazione:
Estrarre questo ZIP dentro:
C:\Users\Davide\Desktop\ProgettoTR-main
accettando la sovrascrittura dei file.

Scopo:
Bloccare il vecchio percorso paper ScoreOnly+Meta_OK che durante la 8h observation ha creato ordini/posizioni fuori dal guarded path.

Nuovi comandi:
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\run_paper_order_leakage_guard.py

Validazione consigliata:
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python -m compileall -q trading_bot

Poi:
python trading_bot\run_paper_order_leakage_guard.py

Nota:
Il report iniziale può restituire WARN perché i vecchi eventi legacy BTC/BNB/ETH sono già presenti nei log. Il criterio importante dopo la patch è che i nuovi segnali legacy vengano bloccati con LEGACY_PAPER_ORDER_BLOCKED e non producano nuovi PAPER_ORDER_FILLED/POSITION_OPENED.

Sicurezza:
NO live
NO testnet
NO exchange broker reale
NO broker submit
NO order submission autorizzata
NO position opening da legacy
NO gate/risk/signal/routing changes
