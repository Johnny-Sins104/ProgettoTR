"""declared_trials.py — Ex-ante trial declaration registry for Edge Research 03.

Cycles 1-2 closed with 84 cumulative declared trials. This program declares
at most 12 configs per family (TSMOM, funding carry), numbered cumulatively
85...108. Running any config that was not declared first raises (fail-closed):
the multiple-testing accounting must be complete BEFORE results exist.

Rules enforced here:
- max 12 configs per family
- one declaration per family (no re-declaration, no incremental additions)
- configs must be frozen dataclasses (immutable after declaration)
- duplicate configs within a declaration raise
- the trial log is emitted to data/research/edge03_trial_log.json
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRIAL_LOG_STARTING_COUNT = 84   # cumulative trials declared in cycles 1-2
MAX_CONFIGS_PER_FAMILY = 12
KNOWN_FAMILIES = ("tsmom", "funding_carry")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRIAL_LOG_PATH = _PROJECT_ROOT / "data" / "research" / "edge03_trial_log.json"

# family -> tuple of declared configs; insertion order defines trial numbers.
_REGISTRY: dict[str, tuple[Any, ...]] = {}


def _require_frozen_dataclass(config: Any) -> None:
    if not dataclasses.is_dataclass(config) or isinstance(config, type):
        raise ValueError(
            f"Declared config must be a dataclass instance, got {config!r}."
        )
    if not type(config).__dataclass_params__.frozen:
        raise ValueError(
            f"Declared config must be a FROZEN dataclass (immutable after "
            f"declaration), got mutable {type(config).__name__}."
        )


def declared_trial_count() -> int:
    """Cumulative trial count including cycles 1-2."""
    return TRIAL_LOG_STARTING_COUNT + sum(len(v) for v in _REGISTRY.values())


def declare_trials(
    family: str,
    configs: tuple[Any, ...],
    *,
    log_path: Path | None = None,
) -> list[int]:
    """Declare the full config grid for a family. One shot, before any run.

    Returns the assigned cumulative trial numbers (e.g. [85, 86, ...]).
    Raises ValueError on any rule violation. Emits/updates the trial log JSON.
    """
    fam = str(family or "").strip().lower()
    if fam not in KNOWN_FAMILIES:
        raise ValueError(
            f"Unknown family {family!r}: must be one of {KNOWN_FAMILIES}."
        )
    if fam in _REGISTRY:
        raise ValueError(
            f"Family {fam!r} already declared ({len(_REGISTRY[fam])} configs). "
            f"Declarations are one-shot: no re-declaration, no additions."
        )
    configs = tuple(configs)
    if not configs:
        raise ValueError(f"Family {fam!r} declaration must contain at least 1 config.")
    if len(configs) > MAX_CONFIGS_PER_FAMILY:
        raise ValueError(
            f"Family {fam!r} declares {len(configs)} configs: "
            f"max {MAX_CONFIGS_PER_FAMILY} per family."
        )
    for c in configs:
        _require_frozen_dataclass(c)
    if len(set(configs)) != len(configs):
        raise ValueError(f"Family {fam!r} declaration contains duplicate configs.")

    start = declared_trial_count() + 1
    _REGISTRY[fam] = configs
    numbers = list(range(start, start + len(configs)))

    _write_trial_log(log_path or DEFAULT_TRIAL_LOG_PATH)
    return numbers


def assert_declared(family: str, config: Any) -> int:
    """Fail-closed run guard: raise unless config was declared for family.

    Returns the cumulative trial number of the config.
    """
    fam = str(family or "").strip().lower()
    declared = _REGISTRY.get(fam)
    if not declared:
        raise ValueError(
            f"No trials declared for family {family!r}: declare_trials() must "
            f"run BEFORE any backtest (ex-ante multiple-testing accounting)."
        )
    if config not in declared:
        raise ValueError(
            f"Config {config!r} was NOT declared for family {fam!r}. "
            f"Undeclared runs are forbidden (fail-closed)."
        )
    offset = TRIAL_LOG_STARTING_COUNT
    for known_fam, cfgs in _REGISTRY.items():
        if known_fam == fam:
            return offset + 1 + cfgs.index(config)
        offset += len(cfgs)
    raise ValueError(f"registry inconsistency for family {fam!r}")  # unreachable


def _write_trial_log(path: Path) -> None:
    entries: list[dict[str, Any]] = []
    offset = TRIAL_LOG_STARTING_COUNT
    for fam, cfgs in _REGISTRY.items():
        for i, cfg in enumerate(cfgs):
            entries.append({
                "trial_number": offset + 1 + i,
                "family": fam,
                "config": dataclasses.asdict(cfg),
            })
        offset += len(cfgs)
    payload = {
        "report_type": "edge03_trial_log",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "starting_count": TRIAL_LOG_STARTING_COUNT,
        "cumulative_count": declared_trial_count(),
        "max_configs_per_family": MAX_CONFIGS_PER_FAMILY,
        "trials": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _reset_registry_for_tests() -> None:
    """Test-only: clear the in-memory registry."""
    _REGISTRY.clear()
