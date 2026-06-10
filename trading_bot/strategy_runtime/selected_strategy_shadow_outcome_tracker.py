from __future__ import annotations

from typing import Any


def build_outcome_tracking_stub(event: dict[str, Any], *, lookahead_candles: int = 12) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "tracking_status": "PENDING",
        "entry_price": event.get("entry_price"),
        "theoretical_sl": event.get("sl"),
        "theoretical_tp": event.get("tp"),
        "lookahead_candles": lookahead_candles,
        "outcome": "UNKNOWN",
        "reason": "outcome_tracking_scaffold_only",
        "shadow_only": True,
        "can_trade": False,
        "would_trade": False,
    }
