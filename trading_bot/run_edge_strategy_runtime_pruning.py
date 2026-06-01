from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.edge_strategy_runtime_pruning import EdgeStrategyRuntimePruningSettings, write_edge_strategy_runtime_pruning_report


def main() -> None:
    data_dir = Path(getattr(Config, "PAPER_EVENTS_PATH", "data/paper_events.jsonl")).parent
    settings = EdgeStrategyRuntimePruningSettings.from_config(Config)
    report = write_edge_strategy_runtime_pruning_report(data_dir, settings)
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "runtime_pruning_events": report.get("runtime_pruning_events"),
        "blocked_signal_count": report.get("blocked_signal_count"),
        "watchlist_signal_count": report.get("watchlist_signal_count"),
        "enabled": report.get("settings", {}).get("enabled"),
        "blocked_archetypes": report.get("settings", {}).get("blocked_archetypes"),
        "watchlist_archetypes": report.get("settings", {}).get("watchlist_archetypes"),
        "report": report.get("report"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
