Prompt 29.4.4s-3 — Archetype pruning + breakeven drag hardening

Extract this patch-only ZIP over the existing ProgettoTR-main folder.

Files included:
- trading_bot/core/edge_strategy_discovery.py
- trading_bot/run_edge_strategy_discovery.py
- trading_bot/test_edge_strategy_discovery.py
- docs/patch_reports/PROMPT_29_4_4S3_ARCHETYPE_PRUNING_BREAKEVEN_DRAG.md
- trading_bot/docs/patch_reports/PROMPT_29_4_4S3_ARCHETYPE_PRUNING_BREAKEVEN_DRAG.md

Validation:
  python -m compileall -q trading_bot
  python trading_bot\test_edge_strategy_discovery.py
  python trading_bot\run_edge_strategy_discovery.py --windows 10000,12000,15000,18000,20000

Safety:
- diagnostic only
- no live/testnet/exchange broker enablement
- no order submission
- no automatic pruning applied to runtime gates
- no threshold lowering or forced trades
