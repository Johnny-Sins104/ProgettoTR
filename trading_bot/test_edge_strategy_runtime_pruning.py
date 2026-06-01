from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.edge_strategy_runtime_pruning import (
    EdgeStrategyRuntimePruningSettings,
    build_runtime_pruning_event,
    evaluate_runtime_archetype_pruning,
    extract_archetype,
    write_edge_strategy_runtime_pruning_report,
)


def test_runtime_pruning_is_diagnostic_only_by_default() -> None:
    settings = EdgeStrategyRuntimePruningSettings()
    decision = evaluate_runtime_archetype_pruning(settings, archetype="RANGING_MEAN_REVERSION")
    assert decision.blocked is False
    assert decision.reason == "blocked_archetype_diagnostic_only"
    event = build_runtime_pruning_event(
        settings,
        cycle_id="pc_test",
        symbol="BTC/USDT",
        side="SELL",
        archetype="RANGING_MEAN_REVERSION",
        score=55,
        confidence={"setup_archetype": "RANGING_MEAN_REVERSION", "ai_prob": 52.0},
    )
    assert event["event_type"] == "EDGE_STRATEGY_ARCHETYPE_PRUNING_AUDIT"
    assert event["blocked"] is False
    assert event["settings_enabled"] is False
    assert event["orders_submitted_by_pruning"] == 0
    assert event["positions_opened_by_pruning"] == 0


def test_runtime_pruning_blocks_only_when_explicitly_enabled() -> None:
    settings = EdgeStrategyRuntimePruningSettings(enabled=True, blocked_archetypes=("RANGING_MEAN_REVERSION",))
    blocked = evaluate_runtime_archetype_pruning(settings, archetype="RANGING_MEAN_REVERSION")
    allowed = evaluate_runtime_archetype_pruning(settings, archetype="LIQUIDITY_SWEEP_REVERSAL")
    assert blocked.blocked is True
    assert blocked.reason == "blocked_by_edge_strategy_pruning"
    assert allowed.blocked is False
    assert allowed.watchlist is True


def test_extract_archetype_from_common_signal_payloads() -> None:
    assert extract_archetype({"setup_archetype": "ranging_mean_reversion"}) == "RANGING_MEAN_REVERSION"
    assert extract_archetype({"confidence": {"archetype": "liquidity_sweep_reversal"}}) == "LIQUIDITY_SWEEP_REVERSAL"
    assert extract_archetype({"foo": "bar"}) == "UNKNOWN"


def test_runtime_pruning_report_aggregates_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        events = [
            build_runtime_pruning_event(
                EdgeStrategyRuntimePruningSettings(enabled=True),
                cycle_id="pc_1",
                symbol="BTC/USDT",
                side="SELL",
                archetype="RANGING_MEAN_REVERSION",
            ),
            build_runtime_pruning_event(
                EdgeStrategyRuntimePruningSettings(enabled=False),
                cycle_id="pc_2",
                symbol="ETH/USDT",
                side="BUY",
                archetype="LIQUIDITY_SWEEP_REVERSAL",
            ),
        ]
        path = data / "paper_events.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        report = write_edge_strategy_runtime_pruning_report(data, EdgeStrategyRuntimePruningSettings(enabled=True))
        assert report["runtime_pruning_events"] == 2
        assert report["blocked_signal_count"] == 1
        assert report["watchlist_signal_count"] == 1
        assert report["by_archetype"]["RANGING_MEAN_REVERSION"]["blocked"] == 1
        assert (data / "edge_strategy_runtime_pruning_report.json").exists()


if __name__ == "__main__":
    test_runtime_pruning_is_diagnostic_only_by_default()
    test_runtime_pruning_blocks_only_when_explicitly_enabled()
    test_extract_archetype_from_common_signal_payloads()
    test_runtime_pruning_report_aggregates_events()
    print("Edge strategy runtime pruning tests passed.")
