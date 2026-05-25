"""Prompt 29.4.4 paper-only unlock gate utilities.

This module converts a very small, explicitly configured subset of shadow
candidates into real paper-trading entries.  It is deliberately exchange-free
and live-blocked.  It never changes the core DecisionEngine thresholds; it only
wraps rejected paper diagnostics when the operator enables the paper-only flag.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _csv(value: str | None, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    out = [x.strip() for x in str(value).replace(";", ",").split(",") if x.strip()]
    return out or list(default or [])


@dataclass(frozen=True)
class PaperUnlockGateSettings:
    enabled: bool = False
    profile: str = "BTC_ONLY_40_Q60"
    allowed_symbols: tuple[str, ...] = ("BTC/USDT",)
    allowed_filters: tuple[str, ...] = ("META_PROB_LOW",)
    min_ai_prob: float = 40.0
    min_setup_quality: float = 60.0
    require_tech_gate: bool = True
    max_positions: int = 1
    live_block: bool = True
    tag: str = "PAPER_UNLOCK_29_4_4"

    @classmethod
    def from_config(cls, config: Any, *, enabled: bool | None = None, profile: str | None = None) -> "PaperUnlockGateSettings":
        cfg_profile = str(profile or getattr(config, "PAPER_UNLOCK_PROFILE", "BTC_ONLY_40_Q60") or "BTC_ONLY_40_Q60")
        return cls(
            enabled=bool(getattr(config, "PAPER_ENTRY_UNLOCK_ENABLED", False) if enabled is None else enabled),
            profile=cfg_profile,
            allowed_symbols=tuple(_csv(getattr(config, "PAPER_UNLOCK_ALLOWED_SYMBOLS", "BTC/USDT"), ["BTC/USDT"])),
            allowed_filters=tuple(_csv(getattr(config, "PAPER_UNLOCK_ALLOWED_FILTERS", "META_PROB_LOW"), ["META_PROB_LOW"])),
            min_ai_prob=_safe_float(getattr(config, "PAPER_UNLOCK_MIN_AI_PROB", 40.0), 40.0),
            min_setup_quality=_safe_float(getattr(config, "PAPER_UNLOCK_MIN_SETUP_QUALITY", 60.0), 60.0),
            require_tech_gate=bool(getattr(config, "PAPER_UNLOCK_REQUIRE_TECH_GATE", True)),
            max_positions=max(1, int(getattr(config, "PAPER_UNLOCK_MAX_POSITIONS", 1) or 1)),
            live_block=bool(getattr(config, "PAPER_UNLOCK_LIVE_BLOCK", True)),
            tag=str(getattr(config, "PAPER_UNLOCK_TAG", "PAPER_UNLOCK_29_4_4") or "PAPER_UNLOCK_29_4_4"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_symbols"] = list(self.allowed_symbols)
        data["allowed_filters"] = list(self.allowed_filters)
        return data


@dataclass(frozen=True)
class PaperUnlockDecision:
    accepted: bool
    reason: str
    side: str = ""
    profile: str = ""
    symbol: str = ""
    ai_prob: float = 0.0
    setup_quality: float = 0.0
    technical_score: float = 0.0
    active_score_threshold: float = 0.0
    dominant_filter: str = ""
    tag: str = "PAPER_UNLOCK_29_4_4"
    missing: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_paper_unlock(
    *,
    settings: PaperUnlockGateSettings,
    signal_diagnostic: dict[str, Any] | None,
    symbol: str,
    mode: str = "paper",
    duplicate_candle: bool = False,
    open_positions_count: int = 0,
) -> PaperUnlockDecision:
    """Return an auditable paper-unlock decision for one diagnostic row."""
    if not settings.enabled:
        return PaperUnlockDecision(False, "disabled", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if settings.live_block and str(mode).lower() != "paper":
        return PaperUnlockDecision(False, "live_block", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if not settings.profile:
        return PaperUnlockDecision(False, "empty_profile", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if symbol not in settings.allowed_symbols:
        return PaperUnlockDecision(False, "symbol_not_allowed", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if open_positions_count >= settings.max_positions:
        return PaperUnlockDecision(False, "unlock_max_positions", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if duplicate_candle:
        return PaperUnlockDecision(False, "duplicate_candle", profile=settings.profile, symbol=symbol, tag=settings.tag)
    if not isinstance(signal_diagnostic, dict) or not signal_diagnostic:
        return PaperUnlockDecision(False, "missing_signal_diagnostic", profile=settings.profile, symbol=symbol, tag=settings.tag)

    side = str(signal_diagnostic.get("intended_side") or "").upper()
    if side not in {"BUY", "SELL"}:
        return PaperUnlockDecision(False, "no_intended_side", profile=settings.profile, symbol=symbol, tag=settings.tag)

    dominant_filter = str(signal_diagnostic.get("dominant_filter") or "")
    if settings.allowed_filters and dominant_filter not in settings.allowed_filters:
        return PaperUnlockDecision(False, f"filter_not_allowed:{dominant_filter or '-'}", side=side, profile=settings.profile, symbol=symbol, dominant_filter=dominant_filter, tag=settings.tag)

    ai_prob = _safe_float(signal_diagnostic.get("ai_prob"), 0.0)
    setup_quality = _safe_float(signal_diagnostic.get("setup_quality"), 0.0)
    technical_score = _safe_float(signal_diagnostic.get("technical_score"), 0.0)
    thresholds = signal_diagnostic.get("thresholds") if isinstance(signal_diagnostic.get("thresholds"), dict) else {}
    active_score_threshold = _safe_float(thresholds.get("active_score_threshold"), 0.0)

    missing: dict[str, float] = {
        "ai_prob_gap": max(0.0, settings.min_ai_prob - ai_prob),
        "setup_quality_gap": max(0.0, settings.min_setup_quality - setup_quality),
    }
    if settings.require_tech_gate:
        missing["tech_score_gap"] = max(0.0, active_score_threshold - abs(technical_score))

    if ai_prob < settings.min_ai_prob:
        return PaperUnlockDecision(False, "ai_prob_below_unlock_threshold", side=side, profile=settings.profile, symbol=symbol, ai_prob=ai_prob, setup_quality=setup_quality, technical_score=technical_score, active_score_threshold=active_score_threshold, dominant_filter=dominant_filter, tag=settings.tag, missing=missing)
    if setup_quality < settings.min_setup_quality:
        return PaperUnlockDecision(False, "setup_quality_below_unlock_threshold", side=side, profile=settings.profile, symbol=symbol, ai_prob=ai_prob, setup_quality=setup_quality, technical_score=technical_score, active_score_threshold=active_score_threshold, dominant_filter=dominant_filter, tag=settings.tag, missing=missing)
    if settings.require_tech_gate and abs(technical_score) < active_score_threshold:
        return PaperUnlockDecision(False, "technical_gate_not_met", side=side, profile=settings.profile, symbol=symbol, ai_prob=ai_prob, setup_quality=setup_quality, technical_score=technical_score, active_score_threshold=active_score_threshold, dominant_filter=dominant_filter, tag=settings.tag, missing=missing)

    return PaperUnlockDecision(True, "paper_unlock_accepted", side=side, profile=settings.profile, symbol=symbol, ai_prob=ai_prob, setup_quality=setup_quality, technical_score=technical_score, active_score_threshold=active_score_threshold, dominant_filter=dominant_filter, tag=settings.tag, missing=missing)
