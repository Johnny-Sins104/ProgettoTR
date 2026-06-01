"""Bounded JSONL readers used by diagnostic/audit modules.

Avoids loading entire long-running event logs into memory just to inspect the
latest N events.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Iterable
import json


def iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000, require_event_type: bool = False) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            src: Iterable[str]
            if max_lines and max_lines > 0:
                src = deque(fh, maxlen=int(max_lines))
            else:
                src = fh
            out: list[dict[str, Any]] = []
            for line in src:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict) and (not require_event_type or item.get("event_type")):
                    out.append(item)
            return out
    except Exception:
        return []
