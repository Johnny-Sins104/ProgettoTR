Patch-only package: 29.4.4r-2 — Legacy paper position quarantine / clean-state preflight

Extract into C:\Users\Davide\Desktop\ProgettoTR-main and allow overwrite.

Validate:
  python trading_bot\test_paper_legacy_position_quarantine.py
  python trading_bot\test_paper_order_leakage_guard.py

Operator flow:
  python trading_bot\run_paper_legacy_position_quarantine.py --report-only
  python trading_bot\run_paper_legacy_position_quarantine.py --quarantine
  python trading_bot\run_paper_legacy_position_quarantine.py --reset-paper-state --confirm-reset

Reset creates backups in data\paper_legacy_quarantine_backups\ before cleaning active paper state/log files.
No live/testnet/exchange broker. No order submission. No position opening.
