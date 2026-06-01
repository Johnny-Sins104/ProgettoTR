"""Prompt 29.4.4s-4 runtime archetype pruning gate.

Diagnostic-first bridge from the edge-strategy discovery report to the paper
runtime.  The gate is deliberately fail-closed and disabled by default: it can
emit audit events for every detected signal, and it blocks only when the
operator explicitly enables pruning via environment/config.

No live/testnet/exchange broker path is enabled here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from core.jsonl_utils import iter_jsonl_tail

PROMPT_ID = "29.4.4s-4"
EVENT_TYPE = "EDGE_STRATEGY_ARCHETYPE_PRUNING_AUDIT"
REPORT_NAME = "edge_strategy_runtime_pruning_report.json"
DEFAULT_BLOCKED_ARCHETYPES = ("RANGING_MEAN_REVERSION",)
DEFAULT_WATCHLIST_ARCHETYPES = ("LIQUIDITY_SWEEP_REVERSAL",)


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _split_csv(value: Any, default: Iterable[str] = ()) -> tuple[str, ...]:
    if value is None:
        value = ",".join(default)
    if isinstance(value, (list, tuple, set)):
        src = value
    else:
        src = str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    for item in src:
        norm = normalize_archetype(item)
        if norm and norm not in out:
            out.append(norm)
    return tuple(out)


def normalize_archetype(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper().replace(" ", "_")


@dataclass(frozen=True)
class EdgeStrategyRuntimePruningSettings:
    enabled: bool = False
    audit_enabled: bool = True
    fail_closed: bool = True
    blocked_archetypes: tuple[str, ...] = DEFAULT_BLOCKED_ARCHETYPES
    watchlist_archetypes: tuple[str, ...] = DEFAULT_WATCHLIST_ARCHETYPES
    report_name: str = REPORT_NAME
    max_report_events: int = 50000

    @classmethod
    def from_config(cls, config: Any | None = None) -> "EdgeStrategyRuntimePruningSettings":
        import os

        def cfg(name: str, default: Any) -> Any:
            if name in os.environ:
                return os.environ.get(name)
            if config is not None and hasattr(config, name):
                return getattr(config, name)
            return default

        return cls(
            enabled=_bool(cfg("EDGE_STRATEGY_PRUNING_ENABLED", "0"), False),
            audit_enabled=_bool(cfg("EDGE_STRATEGY_PRUNING_AUDIT_ENABLED", "1"), True),
            fail_closed=_bool(cfg("EDGE_STRATEGY_PRUNING_FAIL_CLOSED", "1"), True),
            blocked_archetypes=_split_csv(
                cfg("EDGE_STRATEGY_BLOCKED_ARCHETYPES", ",".join(DEFAULT_BLOCKED_ARCHETYPES)),
                DEFAULT_BLOCKED_ARCHETYPES,
            ),
            watchlist_archetypes=_split_csv(
                cfg("EDGE_STRATEGY_WATCHLIST_ARCHETYPES", ",".join(DEFAULT_WATCHLIST_ARCHETYPES)),
                DEFAULT_WATCHLIST_ARCHETYPES,
            ),
            report_name=str(cfg("EDGE_STRATEGY_RUNTIME_PRUNING_REPORT", REPORT_NAME) or REPORT_NAME),
            max_report_events=int(float(cfg("EDGE_STRATEGY_PRUNING_MAX_REPORT_EVENTS", "50000") or 50000)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blocked_archetypes"] = list(self.blocked_archetypes)
        data["watchlist_archetypes"] = list(self.watchlist_archetypes)
        return data


@dataclass(frozen=True)
class EdgeStrategyPruningDecision:
    archetype: str
    blocked: bool
    watchlist: bool
    reason: str
    settings_enabled: bool
    audit_enabled: bool
    fail_closed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_archetype(*sources: Any) -> str:
    """Best-effort extraction of the selected strategy archetype.

    Different pipeline stages use different keys.  The function is intentionally
    conservative: if no explicit archetype exists, the decision becomes UNKNOWN
    and the gate will not block it.
    """
    keys = (
        "setup_archetype",
        "archetype",
        "combination",
        "structure_archetype",
        "selected_archetype",
    )
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if source.get(key):
                return normalize_archetype(source.get(key))
        nested = source.get("confidence")
        if isinstance(nested, dict):
            found = extract_archetype(nested)
            if found != "UNKNOWN":
                return found
    return "UNKNOWN"


def evaluate_runtime_archetype_pruning(
    settings: EdgeStrategyRuntimePruningSettings,
    *,
    archetype: Any,
) -> EdgeStrategyPruningDecision:
    arch = normalize_archetype(archetype)
    is_blocked_archetype = arch in set(settings.blocked_archetypes)
    is_watchlist_archetype = arch in set(settings.watchlist_archetypes)
    blocked = bool(settings.enabled and settings.fail_closed and is_blocked_archetype)
    if blocked:
        reason = "blocked_by_edge_strategy_pruning"
    elif is_blocked_archetype:
        reason = "blocked_archetype_diagnostic_only"
    elif is_watchlist_archetype:
        reason = "watchlist_archetype_diagnostic_only"
    else:
        reason = "archetype_allowed_or_unknown"
    return EdgeStrategyPruningDecision(
        archetype=arch,
        blocked=blocked,
        watchlist=is_watchlist_archetype,
        reason=reason,
        settings_enabled=bool(settings.enabled),
        audit_enabled=bool(settings.audit_enabled),
        fail_closed=bool(settings.fail_closed),
    )


def build_runtime_pruning_event(
    settings: EdgeStrategyRuntimePruningSettings,
    *,
    cycle_id: str = "",
    symbol: str = "",
    side: str = "",
    archetype: Any = "UNKNOWN",
    source_path: str = "paper_runtime_signal",
    paper_unlock: bool = False,
    score: Any = None,
    confidence: Any = None,
) -> dict[str, Any]:
    decision = evaluate_runtime_archetype_pruning(settings, archetype=archetype)
    return {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT_ID,
        "cycle_id": str(cycle_id or ""),
        "symbol": str(symbol or ""),
        "side": str(side or ""),
        "archetype": decision.archetype,
        "source_path": str(source_path or "paper_runtime_signal"),
        "paper_unlock": bool(paper_unlock),
        "blocked": bool(decision.blocked),
        "watchlist": bool(decision.watchlist),
        "reason": decision.reason,
        "settings_enabled": bool(settings.enabled),
        "audit_enabled": bool(settings.audit_enabled),
        "fail_closed": bool(settings.fail_closed),
        "blocked_archetypes": list(settings.blocked_archetypes),
        "watchlist_archetypes": list(settings.watchlist_archetypes),
        "orders_submitted_by_pruning": 0,
        "positions_opened_by_pruning": 0,
        "score": score,
        "confidence_summary": _confidence_summary(confidence),
    }


def _confidence_summary(confidence: Any) -> dict[str, Any]:
    if not isinstance(confidence, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("ai_prob", "setup_quality", "tech_score", "regime", "setup_archetype", "archetype"):
        if key in confidence:
            out[key] = confidence.get(key)
    return out


def write_edge_strategy_runtime_pruning_report(
    data_dir: str | Path,
    settings: EdgeStrategyRuntimePruningSettings | None = None,
) -> dict[str, Any]:
    settings = settings or EdgeStrategyRuntimePruningSettings.from_config()
    data_path = Path(data_dir)
    events = iter_jsonl_tail(
        data_path / "paper_events.jsonl",
        max_lines=max(1, int(settings.max_report_events)),
        require_event_type=True,
    )
    pruning_events = [e for e in events if e.get("event_type") == EVENT_TYPE]
    blocked_events = [e for e in pruning_events if bool(e.get("blocked"))]
    watchlist_events = [e for e in pruning_events if bool(e.get("watchlist"))]
    by_archetype: dict[str, dict[str, int]] = {}
    for event in pruning_events:
        arch = normalize_archetype(event.get("archetype"))
        row = by_archetype.setdefault(arch, {"events": 0, "blocked": 0, "watchlist": 0})
        row["events"] += 1
        row["blocked"] += int(bool(event.get("blocked")))
        row["watchlist"] += int(bool(event.get("watchlist")))

    status = "PASS"
    if settings.enabled and not settings.blocked_archetypes:
        status = "WARN"
    decision = "EDGE_STRATEGY_RUNTIME_PRUNING_ACTIVE" if settings.enabled else "EDGE_STRATEGY_RUNTIME_PRUNING_DIAGNOSTIC_ONLY"
    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "settings": settings.to_dict(),
        "runtime_pruning_events": len(pruning_events),
        "blocked_signal_count": len(blocked_events),
        "watchlist_signal_count": len(watchlist_events),
        "orders_submitted_by_pruning": 0,
        "positions_opened_by_pruning": 0,
        "by_archetype": dict(sorted(by_archetype.items())),
        "latest_cycle_id": str(pruning_events[-1].get("cycle_id") or "") if pruning_events else "",
        "safety_note": "Diagnostic by default. Blocks only when EDGE_STRATEGY_PRUNING_ENABLED=1 and fail-closed settings are active. Does not enable live/testnet/exchange broker.",
        "report": str(data_path / settings.report_name),
    }
    try:
        (data_path / settings.report_name).write_text(__import__("json").dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass
    return report
