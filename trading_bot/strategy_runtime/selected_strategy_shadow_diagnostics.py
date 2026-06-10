from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from trading_bot.strategy_runtime.selected_strategy_shadow_journal import read_shadow_events


def build_selected_strategy_shadow_stats(data_dir: Path, *, strategy: str | None = None, tail: int = 5000) -> dict[str, Any]:
    events = read_shadow_events(data_dir, tail=tail)
    if strategy:
        events = [event for event in events if event.get("active_strategy") == strategy]
    counts = Counter(str(event.get("signal", "WAIT")) for event in events)
    scores = []
    for event in events:
        try:
            scores.append(float(event.get("score", 0.0)))
        except Exception:
            pass
    latest = events[-1] if events else {}
    selected_strategy = strategy or str(latest.get("active_strategy") or "")
    return {
        "strategy": selected_strategy,
        "events_total": len(events),
        "buy_signals": counts.get("BUY", 0),
        "sell_signals": counts.get("SELL", 0),
        "wait_signals": counts.get("WAIT", 0),
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
        "last_signal": latest.get("signal", "WAIT") if latest else "WAIT",
        "last_score": latest.get("score", 0) if latest else 0,
        "shadow_only": True,
        "can_trade": False,
        "would_trade": False,
    }
