"""Edge Research Program 03 — TSMOM (4h/1d) + funding carry. RESEARCH LAB ONLY.

This package is diagnostic-only and must never be imported by any runtime
module (clean_bot/paper_live.py, main.py, launchers). A dedicated test
asserts the isolation.
"""

DIAGNOSTIC_ONLY: bool = True
OPENS_ORDERS: bool = False
LIVE_TRADING_ALLOWED: bool = False
PAPER_TRADING_ACTIVATION_ALLOWED: bool = False
