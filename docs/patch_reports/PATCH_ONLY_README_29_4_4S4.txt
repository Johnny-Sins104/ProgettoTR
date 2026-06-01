ProgettoTR 29.4.4s-4 — Apply diagnostic archetype pruning to paper/runtime gates

Extract this patch-only ZIP into the project root:
C:\Users\Davide\Desktop\ProgettoTR-main

Then run:
python -m compileall -q trading_bot
python trading_bot\test_edge_strategy_runtime_pruning.py
python trading_bot\test_edge_strategy_discovery.py
python trading_bot\run_edge_strategy_runtime_pruning.py

Default mode is diagnostic-only:
EDGE_STRATEGY_PRUNING_ENABLED=0

No live/testnet/exchange broker is enabled by this patch.
