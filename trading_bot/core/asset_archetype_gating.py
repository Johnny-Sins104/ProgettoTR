"""Prompt 28.11 — asset/archetype-specific robustness gates.

These gates are intentionally conservative and are based on the 28.10
execution-cost stress matrix.  They do not invent new signals; they only block
asset/archetype combinations that failed cost robustness, especially under the
conservative/severe execution models used before paper trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssetArchetypeGateDecision:
    allowed: bool
    reason: str = ""
    rule: str = ""
    details: dict[str, Any] | None = None


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper().replace(":USDT", "")
    if "/" not in value and value.endswith("USDT"):
        value = value[:-4] + "/USDT"
    return value


def normalize_archetype(archetype: str) -> str:
    return str(archetype or "UNKNOWN").strip().upper()


def parse_symbol_list(raw: str) -> list[str]:
    return [normalize_symbol(x) for x in str(raw or "").replace(";", ",").split(",") if str(x).strip()]


def _parse_rule_map(raw: str) -> dict[str, set[str]]:
    """Parse rules like ``ETH/USDT:LIQUIDITY_SWEEP_REVERSAL|SOLUSDT:FOO,BAR``."""
    out: dict[str, set[str]] = {}
    for chunk in str(raw or "").replace(";", "|").split("|"):
        if not chunk.strip() or ":" not in chunk:
            continue
        symbol_part, arches_part = chunk.split(":", 1)
        symbol = normalize_symbol(symbol_part)
        arches = {normalize_archetype(x) for x in arches_part.split(",") if x.strip()}
        if symbol and arches:
            out.setdefault(symbol, set()).update(arches)
    return out


def evaluate_asset_archetype_gate(config: Any, *, symbol: str, archetype: str, cost_model: str | None = None) -> AssetArchetypeGateDecision:
    """Return whether an asset/archetype pair is allowed for the active run.

    Defaults encode the 28.10 stress findings:
    - XRP is research-only for paper/cost-stress runs.
    - ETH and SOL keep mean-reversion but block liquidity sweeps under
      conservative/severe costs.
    - BTC and BNB keep both current positive archetypes.
    """
    if not bool(getattr(config, "ASSET_ARCHETYPE_GATING_ENABLED", True)):
        return AssetArchetypeGateDecision(True, details={"enabled": False})

    sym = normalize_symbol(symbol or getattr(config, "SYMBOL", ""))
    arch = normalize_archetype(archetype)
    model = str(cost_model or getattr(config, "EXECUTION_COST_MODEL", "base") or "base").lower()

    # Paper universe is a deployment guardrail, not a research ban.  By default
    # it is enforced only once execution-cost models are active or when the
    # runner explicitly asks for paper-universe symbols.
    paper_universe = set(parse_symbol_list(getattr(config, "PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT")))
    excluded = set(parse_symbol_list(getattr(config, "PAPER_EXCLUDED_ASSETS", "XRP/USDT")))
    enforce_universe = bool(getattr(config, "PAPER_ASSET_UNIVERSE_ENFORCED", False)) or model in {"conservative", "severe"}
    if enforce_universe and (sym in excluded or (paper_universe and sym not in paper_universe)):
        return AssetArchetypeGateDecision(
            False,
            reason="asset_excluded_from_paper_universe_" + sym.replace("/", "").lower(),
            rule="paper_asset_universe",
            details={"symbol": sym, "cost_model": model, "paper_universe": sorted(paper_universe), "excluded_assets": sorted(excluded)},
        )

    # Cost-sensitive archetype blacklist.  Applies to conservative/severe by default.
    default_rules = "ETH/USDT:LIQUIDITY_SWEEP_REVERSAL|SOL/USDT:LIQUIDITY_SWEEP_REVERSAL|XRP/USDT:LIQUIDITY_SWEEP_REVERSAL"
    rules = _parse_rule_map(getattr(config, "COST_ROBUSTNESS_DISABLED_ASSET_ARCHETYPES", default_rules))
    active_models = {x.strip().lower() for x in str(getattr(config, "COST_ROBUSTNESS_GATE_COST_MODELS", "conservative,severe") or "").split(",") if x.strip()}
    if model in active_models and arch in rules.get(sym, set()):
        return AssetArchetypeGateDecision(
            False,
            reason="asset_archetype_cost_robustness_block_" + sym.replace("/", "").lower() + "_" + arch.lower(),
            rule="asset_archetype_cost_robustness",
            details={"symbol": sym, "archetype": arch, "cost_model": model, "blocked_archetypes": sorted(rules.get(sym, set()))},
        )

    return AssetArchetypeGateDecision(True, details={"symbol": sym, "archetype": arch, "cost_model": model})
