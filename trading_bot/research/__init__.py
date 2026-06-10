"""Edge research laboratory (STRAT-02/03) — separate from the runtime.

Diagnostic-only: never opens orders, never touches live/testnet/exchange,
never reads private keys. Reuses the clean_bot trade models, gap policy and
UnifiedCostModel; extends execution causally from 15m signals to 5m fills.
"""
