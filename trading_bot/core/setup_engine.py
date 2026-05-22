"""
core/setup_engine.py — Market-structure setup engine refactor
===============================================================

Prompt 27 scope
---------------
This module upgrades the legacy indicator-heavy setup quality score with
causal market-structure context.  It is deliberately conservative: it does
not manufacture signals, it classifies and reprices existing technical
candidates so the meta model receives better setup-quality information.

Design principles
-----------------
1. No future data: only fields already present on the current candle are read.
2. Diagnostic-first: the engine returns an archetype, score and reasons.
3. Backward compatible: callers can keep using SetupFilter.evaluate_setup().
4. Edge-aware: setup quality is improved only when structure confirms the side.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Tuple
import math

try:
    from config import Config
except Exception:  # pragma: no cover - keeps module importable in isolated tests
    Config = None


@dataclass
class StructureSetupResult:
    side: str
    archetype: str
    structure_score: float
    enhanced_quality: float
    edge_adjustment_r: float
    reasons: list[str] = field(default_factory=list)
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarketStructureSetupEngine:
    """Classifies candidate setups using liquidity, volatility and HTF context."""

    @staticmethod
    def _get(row: Any, key: str, default: Any = 0.0) -> Any:
        try:
            if isinstance(row, dict):
                return row.get(key, default)
            return row.get(key, default)
        except Exception:
            return default

    @classmethod
    def _f(cls, row: Any, key: str, default: float = 0.0) -> float:
        try:
            x = float(cls._get(row, key, default) or default)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    @classmethod
    def _b(cls, row: Any, key: str, default: bool = False) -> bool:
        val = cls._get(row, key, default)
        if isinstance(val, str):
            return val.strip().lower() in {"1", "true", "yes", "y"}
        return bool(val)

    @staticmethod
    def _clip(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(x)))

    @staticmethod
    def _cfg(name: str, default: float) -> float:
        try:
            return float(getattr(Config, name, default)) if Config is not None else float(default)
        except Exception:
            return float(default)

    @staticmethod
    def _cfg_bool(name: str, default: bool) -> bool:
        try:
            return bool(getattr(Config, name, default)) if Config is not None else bool(default)
        except Exception:
            return bool(default)

    @classmethod
    def _has_key(cls, row: Any, key: str) -> bool:
        try:
            if isinstance(row, dict):
                return key in row and row.get(key) is not None
            if hasattr(row, "index"):
                return key in row.index and row.get(key) is not None
            return False
        except Exception:
            return False

    @classmethod
    def _has_any(cls, row: Any, aliases: Iterable[str]) -> bool:
        return any(cls._has_key(row, k) for k in aliases)

    @classmethod
    def feature_audit(cls, row: Any) -> Dict[str, Any]:
        """Audit whether runtime candles carry the market-structure columns.

        Prompt 28.2: the setup engine can only unlock non-mean-reversion
        archetypes if the backtest row actually contains the source features.
        This audit is exported through SignalDensity so missing feature paths are
        visible instead of being mistaken for weak strategy logic.
        """
        groups: Dict[str, list[tuple[str, tuple[str, ...]]]] = {
            "LIQUIDITY_SWEEP_REVERSAL": [
                ("liquidity_sweep_score", ("liquidity_sweep_score",)),
                ("sweep_low", ("sweep_low",)),
                ("sweep_high", ("sweep_high",)),
            ],
            "VOL_COMPRESSION_BREAKOUT": [
                ("volatility_compression", ("volatility_compression", "is_vol_compressed")),
                ("volatility_expansion", ("is_vol_expanding", "range_z_1d")),
                ("volume_z_1d", ("volume_z_1d",)),
            ],
            "HTF_ALIGNED_PULLBACK": [
                ("htf_context", ("htf_trend_alignment", "htf_4h_trend", "htf_1h_trend", "htf_4h_return", "htf_1h_return")),
            ],
            "SESSION_MOMENTUM": [
                ("session_context", ("session_london", "session_ny", "session_overlap_london_ny", "session_asia")),
                ("volume_z_1d", ("volume_z_1d",)),
                ("beta_context", ("btc_return_1", "asset_vs_btc_return_1")),
            ],
            "RANGING_MEAN_REVERSION": [
                ("regime", ("market_regime", "regime")),
                ("band_position", ("bb_position", "range_pos_400")),
                ("rsi", ("rsi_14", "rsi")),
                ("sr_context", ("near_support", "near_resistance", "near_sr")),
            ],
        }
        per_arch: Dict[str, Any] = {}
        total = 0
        present = 0
        for arch, reqs in groups.items():
            missing: list[str] = []
            arch_present = 0
            for canonical, aliases in reqs:
                total += 1
                if cls._has_any(row, aliases):
                    present += 1
                    arch_present += 1
                else:
                    missing.append(canonical)
            per_arch[arch] = {
                "present": arch_present,
                "required": len(reqs),
                "missing": missing,
                "coverage_pct": round((arch_present / len(reqs) * 100.0) if reqs else 0.0, 4),
            }
        ms_keys = [
            "liquidity_sweep_score", "sweep_low", "sweep_high",
            "volatility_compression", "is_vol_compressed", "is_vol_expanding",
            "htf_trend_alignment", "htf_4h_return", "htf_1h_return",
            "volume_z_1d", "range_z_1d", "session_london", "session_ny",
            "session_overlap_london_ny", "btc_return_1", "asset_vs_btc_return_1",
        ]
        runtime_ms_available = any(cls._has_key(row, k) for k in ms_keys)
        return {
            "runtime_market_structure_available": bool(runtime_ms_available),
            "overall_coverage_pct": round((present / total * 100.0) if total else 0.0, 4),
            "by_archetype": per_arch,
        }

    @classmethod
    def evaluate_candidates(cls, row: Any, side: str) -> list[Tuple[str, float, list[str], Dict[str, float]]]:
        """Return raw archetype scores before final penalty.

        This is used by Prompt 28 diagnostics to explain why the engine keeps
        selecting one archetype, instead of only reporting the winner.
        """
        return [
            cls._liquidity_sweep_reversal(row, side),
            cls._volatility_compression_breakout(row, side),
            cls._htf_aligned_pullback(row, side),
            cls._ranging_mean_reversion(row, side),
            cls._session_momentum(row, side),
        ]

    @classmethod
    def evaluate(cls, row: Any, side: str, base_quality: float = 50.0) -> StructureSetupResult:
        side = str(side or "").upper()
        if side not in {"BUY", "SELL"}:
            return StructureSetupResult(side=side, archetype="INVALID", structure_score=0.0, enhanced_quality=0.0, edge_adjustment_r=0.0)

        candidates = cls.evaluate_candidates(row, side)
        archetype, raw_score, reasons, selected_components = cls._select_archetype(candidates)

        feature_audit = cls.feature_audit(row) if cls._cfg_bool("SETUP_MARKET_STRUCTURE_AUDIT", True) else {}
        runtime_ms_available = bool(feature_audit.get("runtime_market_structure_available", False))

        penalty = cls._penalty(row, side)
        score = cls._clip(raw_score - penalty, 0.0, 100.0)

        weak_mean_reversion_fallback = False
        if archetype == "RANGING_MEAN_REVERSION" and cls._cfg_bool("SETUP_MR_REQUIRE_CONFIRMATION", True):
            mr_min_score = cls._cfg("SETUP_MR_MIN_STRUCTURE_SCORE", 52.0)
            has_reversion_reason = any(r in reasons for r in ("lower_band_reversion", "upper_band_reversion"))
            if (not runtime_ms_available) or score < mr_min_score or not has_reversion_reason:
                weak_mean_reversion_fallback = True
                missing_penalty = cls._cfg("SETUP_MR_MISSING_FEATURE_PENALTY", 10.0) if not runtime_ms_available else 0.0
                penalty += missing_penalty
                score = cls._clip(score - missing_penalty, 0.0, 100.0)
                reasons = list(reasons) + ["weak_mean_reversion_fallback"]

        # Enhancement is intentionally capped.  The ML model still decides; this
        # only reprices setup quality when structure confirms the candidate.
        enhancement = min(18.0, score * 0.22)
        if score < 20:
            enhancement = 0.0
        enhanced_quality = cls._clip(float(base_quality) + enhancement - min(10.0, penalty), 0.0, 100.0)
        edge_adjustment_r = round((score - 50.0) / 500.0, 6)  # -0.10R to +0.10R approx.
        if weak_mean_reversion_fallback:
            edge_adjustment_r = round(edge_adjustment_r - cls._cfg("SETUP_MR_FALLBACK_EDGE_PENALTY_R", 0.08), 6)

        all_scores: Dict[str, float] = {}
        all_raw_scores: Dict[str, float] = {}
        for candidate_name, candidate_score, _candidate_reasons, _candidate_components in candidates:
            all_raw_scores[f"raw_score_{candidate_name}"] = round(float(candidate_score), 6)
            all_scores[f"score_{candidate_name}"] = round(cls._clip(float(candidate_score) - penalty, 0.0, 100.0), 6)

        components: Dict[str, Any] = {}
        components.update({k: round(float(v), 6) for k, v in selected_components.items()})
        components.update(all_raw_scores)
        components.update(all_scores)
        components["penalty"] = round(float(penalty), 6)
        components["weak_mean_reversion_fallback"] = float(bool(weak_mean_reversion_fallback))
        if feature_audit:
            components["runtime_market_structure_available"] = float(bool(feature_audit.get("runtime_market_structure_available", False)))
            components["market_structure_feature_coverage_pct"] = float(feature_audit.get("overall_coverage_pct", 0.0))
            # Store per-archetype missing counts as numeric fields for signal-density aggregation.
            for arch_name, arch_audit in feature_audit.get("by_archetype", {}).items():
                components[f"missing_count_{arch_name}"] = float(len(arch_audit.get("missing", [])))
                components[f"coverage_pct_{arch_name}"] = float(arch_audit.get("coverage_pct", 0.0))
        components["winner_margin"] = round(
            float(raw_score) - sorted([float(c[1]) for c in candidates], reverse=True)[1] if len(candidates) > 1 else float(raw_score),
            6,
        )

        return StructureSetupResult(
            side=side,
            archetype=archetype,
            structure_score=round(score, 6),
            enhanced_quality=round(enhanced_quality, 6),
            edge_adjustment_r=edge_adjustment_r,
            reasons=reasons,
            components=components,
        )

    @classmethod
    def _select_archetype(cls, candidates: list[Tuple[str, float, list[str], Dict[str, float]]]) -> Tuple[str, float, list[str], Dict[str, float]]:
        """Select the most specific structural archetype when scores are close.

        Mean reversion has a naturally high baseline on ranging data.  Prompt
        28.1 prevents it from swallowing every candidate when a more specific
        structural family has enough evidence and is within a configurable
        margin of the raw winner.  This only changes classification/edge
        repricing for existing technical candidates; it does not create trades.
        """
        if not candidates:
            return "UNKNOWN", 0.0, [], {}
        ranked = sorted(candidates, key=lambda x: float(x[1]), reverse=True)
        winner = ranked[0]
        min_score = cls._cfg("SETUP_ARCHETYPE_MIN_SCORE", 32.0)
        margin = cls._cfg("SETUP_ARCHETYPE_SPECIFICITY_MARGIN", 12.0)
        specificity_order = {
            "LIQUIDITY_SWEEP_REVERSAL": 5,
            "VOL_COMPRESSION_BREAKOUT": 4,
            "HTF_ALIGNED_PULLBACK": 3,
            "SESSION_MOMENTUM": 2,
            "RANGING_MEAN_REVERSION": 1,
        }
        eligible = [
            c for c in ranked
            if float(c[1]) >= min_score and (float(winner[1]) - float(c[1])) <= margin
        ]
        if not eligible:
            return winner
        return sorted(eligible, key=lambda x: (specificity_order.get(x[0], 0), float(x[1])), reverse=True)[0]

    @classmethod
    def _side_sign(cls, side: str) -> float:
        return 1.0 if side == "BUY" else -1.0

    @classmethod
    def _htf_confirmed(cls, row: Any, side: str) -> bool:
        # Feature aliases supported by the market-structure feature layer.
        # Earlier code only looked for htf_4h_trend/htf_1h_trend, while the
        # dataset often exposes htf_trend_alignment plus 1h/4h returns.
        eps = cls._cfg("SETUP_HTF_RETURN_EPS", 0.0005)
        alignment = cls._f(row, "htf_trend_alignment", 0.0)
        trend = cls._f(row, "htf_4h_trend", cls._f(row, "htf_1h_trend", 0.0))
        ret_4h = cls._f(row, "htf_4h_return", 0.0)
        ret_1h = cls._f(row, "htf_1h_return", 0.0)

        if side == "BUY":
            return alignment > 0 or trend > 0 or (ret_4h > eps and ret_1h > -eps)
        return alignment < 0 or trend < 0 or (ret_4h < -eps and ret_1h < eps)

    @classmethod
    def _session_boost(cls, row: Any) -> float:
        london = cls._f(row, "session_london", 0.0)
        ny = cls._f(row, "session_ny", 0.0)
        overlap = cls._f(row, "session_overlap_london_ny", 0.0)
        return 5.0 * min(1.0, london + ny) + 5.0 * min(1.0, overlap)

    @classmethod
    def _liquidity_sweep_reversal(cls, row: Any, side: str) -> Tuple[str, float, list[str], Dict[str, float]]:
        sweep_low = cls._f(row, "sweep_low", 0.0)
        sweep_high = cls._f(row, "sweep_high", 0.0)
        sweep_score = cls._f(row, "liquidity_sweep_score", 0.0)
        rsi = cls._f(row, "rsi_14", cls._f(row, "rsi", 50.0))
        regime = str(cls._get(row, "market_regime", cls._get(row, "regime", ""))).upper()
        side_sweep = sweep_low if side == "BUY" else sweep_high

        score = 0.0
        reasons: list[str] = []
        sweep_min = cls._cfg("SETUP_SWEEP_SCORE_MIN", 0.0001)
        if side_sweep > 0 or sweep_score >= sweep_min:
            score += 38.0
            reasons.append("side_liquidity_sweep")
        if sweep_score > 0:
            score += min(22.0, max(4.0, sweep_score * 5000.0))
            reasons.append("sweep_displacement")
        if side == "BUY" and rsi < 45:
            score += 14.0
            reasons.append("buy_oversold_reclaim")
        if side == "SELL" and rsi > 55:
            score += 14.0
            reasons.append("sell_overbought_reject")
        if "RANG" in regime:
            score += 10.0
            reasons.append("ranging_reversal_context")
        score += cls._session_boost(row)
        return "LIQUIDITY_SWEEP_REVERSAL", score, reasons, {"side_sweep": side_sweep, "sweep_score": sweep_score, "rsi": rsi}

    @classmethod
    def _volatility_compression_breakout(cls, row: Any, side: str) -> Tuple[str, float, list[str], Dict[str, float]]:
        compressed = cls._f(row, "is_vol_compressed", 0.0)
        expanding = cls._f(row, "is_vol_expanding", 0.0)
        vol_comp = cls._f(row, "volatility_compression", 1.0)
        volume_z = cls._f(row, "volume_z_1d", 0.0)
        range_z = cls._f(row, "range_z_1d", 0.0)
        htf = cls._htf_confirmed(row, side)
        score = 0.0
        reasons: list[str] = []
        comp_threshold = cls._cfg("SETUP_VOL_COMPRESSION_THRESHOLD", 0.95)
        if compressed > 0 or vol_comp < comp_threshold:
            score += 25.0
            reasons.append("volatility_compression")
        if expanding > 0 or range_z > 0.75:
            score += 20.0
            reasons.append("range_expansion")
        if volume_z > 0.5:
            score += min(18.0, 6.0 + volume_z * 4.0)
            reasons.append("volume_confirmation")
        if htf:
            score += 18.0
            reasons.append("htf_trend_confirmed")
        score += cls._session_boost(row)
        return "VOL_COMPRESSION_BREAKOUT", score, reasons, {"volatility_compression": vol_comp, "volume_z_1d": volume_z, "range_z_1d": range_z}

    @classmethod
    def _htf_aligned_pullback(cls, row: Any, side: str) -> Tuple[str, float, list[str], Dict[str, float]]:
        htf = cls._htf_confirmed(row, side)
        close_vs_ema = cls._f(row, "close_vs_ema", 0.0)
        rsi = cls._f(row, "rsi_14", cls._f(row, "rsi", 50.0))
        vol_expanding = cls._f(row, "is_vol_expanding", 0.0)
        score = 0.0
        reasons: list[str] = []
        if htf:
            score += 35.0
            reasons.append("htf_alignment")
        if side == "BUY" and -1.5 <= close_vs_ema <= 2.5 and 38 <= rsi <= 58:
            score += 22.0
            reasons.append("bull_pullback_zone")
        if side == "SELL" and -2.5 <= close_vs_ema <= 1.5 and 42 <= rsi <= 62:
            score += 22.0
            reasons.append("bear_pullback_zone")
        if vol_expanding <= 0:
            score += 8.0
            reasons.append("not_chasing_vol_expansion")
        score += cls._session_boost(row)
        return "HTF_ALIGNED_PULLBACK", score, reasons, {"close_vs_ema": close_vs_ema, "rsi": rsi, "htf_confirmed": float(htf)}

    @classmethod
    def _ranging_mean_reversion(cls, row: Any, side: str) -> Tuple[str, float, list[str], Dict[str, float]]:
        regime = str(cls._get(row, "market_regime", cls._get(row, "regime", ""))).upper()
        bb = cls._f(row, "bb_position", cls._f(row, "range_pos_400", 0.5))
        rsi = cls._f(row, "rsi_14", cls._f(row, "rsi", 50.0))
        near_support = cls._b(row, "near_support", False) or cls._f(row, "near_sr", 0.0) > 0
        near_resistance = cls._b(row, "near_resistance", False) or cls._f(row, "near_sr", 0.0) > 0
        score = 0.0
        reasons: list[str] = []
        if "RANG" in regime or "TRANS" in regime:
            score += 25.0
            reasons.append("range_or_transition_context")
        if side == "BUY" and (bb < 0.25 or rsi < 42 or near_support):
            score += 28.0
            reasons.append("lower_band_reversion")
        if side == "SELL" and (bb > 0.75 or rsi > 58 or near_resistance):
            score += 28.0
            reasons.append("upper_band_reversion")
        if cls._f(row, "is_vol_expanding", 0.0) <= 0:
            score += 10.0
            reasons.append("stable_vol_for_mean_reversion")
        return "RANGING_MEAN_REVERSION", score, reasons, {"bb_position": bb, "rsi": rsi}

    @classmethod
    def _session_momentum(cls, row: Any, side: str) -> Tuple[str, float, list[str], Dict[str, float]]:
        htf = cls._htf_confirmed(row, side)
        session = cls._session_boost(row)
        volume_z = cls._f(row, "volume_z_1d", 0.0)
        btc_ret = cls._f(row, "btc_return_1", 0.0)
        asset_rel = cls._f(row, "asset_vs_btc_return_1", 0.0)
        sign = cls._side_sign(side)
        score = 0.0
        reasons: list[str] = []
        if session >= 5:
            score += 18.0
            reasons.append("active_session")
        if htf:
            score += 22.0
            reasons.append("htf_confirmed")
        if volume_z > 0.5:
            score += min(20.0, 8.0 + volume_z * 4.0)
            reasons.append("volume_impulse")
        if sign * (btc_ret + asset_rel) > 0:
            score += 12.0
            reasons.append("market_beta_aligned")
        return "SESSION_MOMENTUM", score, reasons, {"volume_z_1d": volume_z, "btc_return_1": btc_ret, "asset_vs_btc_return_1": asset_rel}

    @classmethod
    def _penalty(cls, row: Any, side: str) -> float:
        penalty = 0.0
        funding_z = abs(cls._f(row, "funding_rate_z", 0.0))
        if funding_z > 2.0:
            penalty += min(10.0, (funding_z - 2.0) * 3.0)
        vol_comp = cls._f(row, "volatility_compression", 1.0)
        if vol_comp > 2.5:
            penalty += 8.0
        htf_trend = cls._f(row, "htf_4h_trend", cls._f(row, "htf_1h_trend", 0.0))
        htf_ret = cls._f(row, "htf_4h_return", cls._f(row, "htf_1h_return", 0.0))
        if (side == "BUY" and (htf_trend < 0 or htf_ret < -cls._cfg("SETUP_HTF_RETURN_EPS", 0.0005))) or (side == "SELL" and (htf_trend > 0 or htf_ret > cls._cfg("SETUP_HTF_RETURN_EPS", 0.0005))):
            penalty += 8.0
        return penalty
