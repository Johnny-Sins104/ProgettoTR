"""Lightweight runtime profiler for backtest research runs."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RuntimeProfiler:
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)
    phases: dict[str, float] = field(default_factory=dict)
    counters: dict[str, Any] = field(default_factory=dict)

    def add_metadata(self, **kwargs: Any) -> None:
        self.metadata.update(kwargs)

    def add_counter(self, name: str, value: Any) -> None:
        self.counters[name] = value

    @contextmanager
    def phase(self, name: str):
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.phases[name] = self.phases.get(name, 0.0) + (time.perf_counter() - t0)

    def total_seconds(self) -> float:
        return time.perf_counter() - self.started_at

    def to_report(self) -> dict[str, Any]:
        phases = {k: round(float(v), 4) for k, v in sorted(self.phases.items())}
        total = round(float(self.total_seconds()), 4)
        return {
            "enabled": bool(self.enabled),
            "metadata": dict(self.metadata),
            "phases_seconds": phases,
            "counters": dict(self.counters),
            "total_runtime_seconds": total,
            "largest_phases": sorted(
                [{"phase": k, "seconds": v} for k, v in phases.items()],
                key=lambda row: row["seconds"],
                reverse=True,
            )[:10],
        }

    def export(self, path: str | Path = "data/runtime_profile_report.json") -> dict[str, Any]:
        report = self.to_report()
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


def get_runtime_profiler(config) -> RuntimeProfiler | None:
    profiler = getattr(config, "RUNTIME_PROFILER", None)
    return profiler if isinstance(profiler, RuntimeProfiler) else None
