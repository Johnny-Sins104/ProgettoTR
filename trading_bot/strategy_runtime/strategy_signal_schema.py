from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


StrategyId = Literal["ema_vwap", "bb", "macd", "ichimoku", "auto"]
SignalSide = Literal["BUY", "SELL", "WAIT"]

SUPPORTED_STRATEGIES: tuple[str, ...] = ("ema_vwap", "bb", "macd", "ichimoku", "auto")


@dataclass(frozen=True)
class SignalCondition:
    name: str
    ok: bool
    value: Any = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategySignal:
    strategy: str
    strategy_label: str = ""
    signal: SignalSide = "WAIT"
    score: float = 0.0
    conditions: list[SignalCondition] = field(default_factory=list)
    entry_price: float | None = None
    sl: float | None = None
    tp: float | None = None
    risk_pct: float | None = None
    blocked: bool = True
    block_reasons: list[str] = field(default_factory=list)
    shadow_only: bool = True
    would_trade: bool = False
    can_trade: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["conditions"] = [condition.to_dict() for condition in self.conditions]
        data["score"] = max(0.0, min(100.0, float(self.score)))
        data["shadow_only"] = True
        data["would_trade"] = False
        data["can_trade"] = False
        return data


def condition(name: str, ok: bool, value: Any = None, reason: str = "") -> SignalCondition:
    return SignalCondition(name=name, ok=bool(ok), value=value, reason=reason)


def make_signal(
    *,
    strategy: str,
    strategy_label: str = "",
    signal: SignalSide = "WAIT",
    score: float = 0.0,
    conditions: list[SignalCondition] | None = None,
    entry_price: float | None = None,
    sl: float | None = None,
    tp: float | None = None,
    risk_pct: float | None = None,
    blocked: bool = True,
    block_reasons: list[str] | None = None,
    shadow_only: bool = True,
    would_trade: bool = False,
    can_trade: bool = False,
) -> dict[str, Any]:
    return StrategySignal(
        strategy=strategy,
        strategy_label=strategy_label,
        signal=signal,
        score=score,
        conditions=conditions or [],
        entry_price=entry_price,
        sl=sl,
        tp=tp,
        risk_pct=risk_pct,
        blocked=blocked,
        block_reasons=block_reasons or [],
        shadow_only=shadow_only,
        would_trade=would_trade,
        can_trade=can_trade,
    ).to_dict()


def wait_signal(strategy: str, reason: str, conditions: list[SignalCondition] | None = None) -> dict[str, Any]:
    return make_signal(
        strategy=strategy,
        signal="WAIT",
        score=0.0,
        conditions=conditions or [],
        blocked=True,
        block_reasons=[reason],
    )


def validate_strategy_id(strategy: str) -> str:
    normalized = str(strategy or "").strip().lower()
    if normalized not in SUPPORTED_STRATEGIES:
        raise ValueError(f"unsupported_strategy:{strategy}")
    return normalized


def has_uniform_signal_schema(signal: dict[str, Any]) -> bool:
    required = {
        "strategy",
        "strategy_label",
        "signal",
        "score",
        "conditions",
        "entry_price",
        "sl",
        "tp",
        "risk_pct",
        "blocked",
        "block_reasons",
        "shadow_only",
        "would_trade",
        "can_trade",
    }
    if not required.issubset(signal):
        return False
    if signal["signal"] not in {"BUY", "SELL", "WAIT"}:
        return False
    if not isinstance(signal["conditions"], list):
        return False
    return isinstance(signal["block_reasons"], list)
