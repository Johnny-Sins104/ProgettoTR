"""Prompt 28.10 — execution realism / slippage stress model.

Deterministic, backtest-safe execution cost model used for stress testing.
Costs are expressed as round-trip basis points and can be converted into
notional PnL drag by the backtest engine.  The model intentionally avoids
randomness so base/conservative/severe runs are reproducible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from config import Config


@dataclass(frozen=True)
class ExecutionCostEstimate:
    cost_model: str
    symbol: str
    timeframe: str
    vol_regime: str
    order_type: str
    entry_type: str
    price: float
    atr_val: float
    atr_pct: float
    atr_ratio: float
    maker_fee_bps_side: float
    taker_fee_bps_side: float
    fee_bps_round_trip: float
    spread_bps_round_trip: float
    slippage_bps_round_trip: float
    latency_bps_round_trip: float
    partial_fill_bps_round_trip: float
    stress_multiplier: float
    timeframe_multiplier: float
    total_round_trip_cost_bps: float
    fill_probability: float

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 8) if isinstance(v, float) else v for k, v in asdict(self).items()}


def normalize_cost_model(name: str | None = None) -> str:
    value = str(name or getattr(Config, "EXECUTION_COST_MODEL", "base") or "base").strip().lower()
    aliases = {
        "normal": "base",
        "default": "base",
        "cons": "conservative",
        "conserv": "conservative",
        "stress": "severe",
        "worst": "severe",
    }
    value = aliases.get(value, value)
    if value not in {"base", "conservative", "severe"}:
        value = "base"
    return value


def _asset_slug(symbol: str | None = None) -> str:
    return str(symbol or getattr(Config, "SYMBOL", "BTC/USDT")).replace("/", "").replace(":", "").lower()


def _asset_spread_bps(symbol: str) -> float:
    # Typical round-trip spread proxy in bps for liquid USDT-M futures.
    slug = _asset_slug(symbol)
    table = {
        "btcusdt": 1.0,
        "ethusdt": 1.2,
        "solusdt": 2.0,
        "bnbusdt": 1.8,
        "xrpusdt": 2.4,
    }
    return float(table.get(slug, 2.0))


def _model_stress_multiplier(model: str) -> float:
    return {
        "base": float(getattr(Config, "EXECUTION_COST_BASE_MULTIPLIER", 1.0)),
        "conservative": float(getattr(Config, "EXECUTION_COST_CONSERVATIVE_MULTIPLIER", 1.75)),
        "severe": float(getattr(Config, "EXECUTION_COST_SEVERE_MULTIPLIER", 2.75)),
    }.get(normalize_cost_model(model), 1.0)


def _timeframe_multiplier(timeframe: str | None = None) -> float:
    tf = str(timeframe or getattr(Config, "TIMEFRAME", "15m")).lower()
    if tf == "5m":
        return float(getattr(Config, "EXECUTION_COST_TIMEFRAME_MULTIPLIER_5M", 1.20))
    if tf == "3m":
        return float(getattr(Config, "EXECUTION_COST_TIMEFRAME_MULTIPLIER_3M", 1.55))
    return float(getattr(Config, "EXECUTION_COST_TIMEFRAME_MULTIPLIER_15M", 1.0))


def _vol_multiplier(regime: str, atr_ratio: float) -> float:
    reg = str(regime or "NORMAL").upper()
    base = {"LOW_VOL": 0.85, "NORMAL": 1.0, "HIGH_VOL": 1.55, "EXTREME": 2.50}.get(reg, 1.0)
    try:
        r = max(0.0, float(atr_ratio or 1.0))
    except Exception:
        r = 1.0
    return max(0.7, min(3.0, base * (0.75 + 0.25 * r)))


class ExecutionCostModel:
    """Deterministic execution-cost model for backtests and stress reports."""

    @staticmethod
    def estimate_round_trip_bps(
        *,
        price: float,
        atr_val: float = 0.0,
        atr_pct: float = 0.0,
        atr_ratio: float = 1.0,
        vol_regime: str = "NORMAL",
        order_type: str = "LIMIT",
        entry_type: str = "BREAKOUT",
        symbol: str | None = None,
        timeframe: str | None = None,
        cost_model: str | None = None,
    ) -> ExecutionCostEstimate:
        model = normalize_cost_model(cost_model)
        symbol = str(symbol or getattr(Config, "SYMBOL", "BTC/USDT"))
        timeframe = str(timeframe or getattr(Config, "TIMEFRAME", "15m"))
        order_type = str(order_type or "LIMIT").upper()
        entry_type = str(entry_type or "BREAKOUT").upper()
        vol_regime = str(vol_regime or "NORMAL").upper()

        maker_fee_side = float(getattr(Config, "EXECUTION_MAKER_FEE_BPS_SIDE", 2.0))
        taker_fee_side = float(getattr(Config, "EXECUTION_TAKER_FEE_BPS_SIDE", 4.0))
        entry_taker = order_type in {"MARKET", "STOP"} or entry_type in {"BREAKOUT", "MARKET"}
        exit_taker = order_type in {"STOP", "MARKET"}
        fee_bps = (taker_fee_side if entry_taker else maker_fee_side) + (taker_fee_side if exit_taker else maker_fee_side)

        spread_bps = _asset_spread_bps(symbol) * _vol_multiplier(vol_regime, atr_ratio)

        try:
            atr_pct_val = float(atr_pct or 0.0)
            if atr_pct_val <= 0.0 and price and atr_val:
                atr_pct_val = abs(float(atr_val) / float(price)) * 100.0
        except Exception:
            atr_pct_val = 0.0
        # Convert ATR% into bps and charge a small deterministic adverse selection fraction.
        atr_bps = max(0.0, atr_pct_val * 100.0)
        if model == "base":
            slip_frac = 0.004
        elif model == "conservative":
            slip_frac = 0.008
        else:
            slip_frac = 0.014
        slippage_bps = min(float(getattr(Config, "EXECUTION_MAX_ATR_SLIPPAGE_BPS", 35.0)), atr_bps * slip_frac)

        latency_bps = 0.0
        if model in {"conservative", "severe"}:
            latency_bps = float(getattr(Config, "EXECUTION_LATENCY_BPS_CONSERVATIVE", 1.0 if model == "conservative" else 2.5))
            if entry_type == "BREAKOUT":
                latency_bps *= 1.35
        partial_bps = 0.0
        if model == "severe":
            partial_bps = float(getattr(Config, "EXECUTION_PARTIAL_FILL_PENALTY_BPS_SEVERE", 2.0))

        stress_mult = _model_stress_multiplier(model)
        tf_mult = _timeframe_multiplier(timeframe)
        variable = (spread_bps + slippage_bps + latency_bps + partial_bps) * stress_mult * tf_mult
        total = max(0.0, fee_bps + variable)
        fill_prob = {"base": 0.98, "conservative": 0.93, "severe": 0.85}.get(model, 0.98)
        if vol_regime == "HIGH_VOL":
            fill_prob -= 0.05
        elif vol_regime == "EXTREME":
            fill_prob -= 0.15
        fill_prob = max(0.50, min(0.995, fill_prob))

        return ExecutionCostEstimate(
            cost_model=model,
            symbol=symbol,
            timeframe=timeframe,
            vol_regime=vol_regime,
            order_type=order_type,
            entry_type=entry_type,
            price=float(price or 0.0),
            atr_val=float(atr_val or 0.0),
            atr_pct=float(atr_pct_val or 0.0),
            atr_ratio=float(atr_ratio or 1.0),
            maker_fee_bps_side=maker_fee_side,
            taker_fee_bps_side=taker_fee_side,
            fee_bps_round_trip=float(fee_bps),
            spread_bps_round_trip=float(spread_bps),
            slippage_bps_round_trip=float(slippage_bps),
            latency_bps_round_trip=float(latency_bps),
            partial_fill_bps_round_trip=float(partial_bps),
            stress_multiplier=float(stress_mult),
            timeframe_multiplier=float(tf_mult),
            total_round_trip_cost_bps=float(total),
            fill_probability=float(fill_prob),
        )

    @staticmethod
    def cost_amount(notional: float, estimate: ExecutionCostEstimate) -> float:
        return max(0.0, float(notional or 0.0)) * float(estimate.total_round_trip_cost_bps) / 10000.0
