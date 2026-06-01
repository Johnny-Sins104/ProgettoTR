"""Summarize the current Git working tree into review buckets.

This tool is intentionally read-only. It helps keep patch commits small by
separating source files, tests, patch documentation, generated outputs, and
deleted tracked files before staging.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


def _git_status() -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    rows: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:].strip()
        rows.append((status, path))
    return rows


def _bucket(status: str, path: str) -> str:
    p = path.replace("\\", "/")
    name = Path(p).name

    if status.strip() == "D":
        return "tracked_deleted"
    if "M" in status:
        return "tracked_modified"
    if not status.startswith("??"):
        return "other_tracked_state"

    if p.endswith(".zip") or name in {"patch_reports.zip"}:
        return "untracked_generated_archive"
    if name.startswith("console_once") and name.endswith(".txt"):
        return "untracked_console_output"
    if p.startswith("docs/patch_reports/") or p.startswith("trading_bot/docs/"):
        return "untracked_patch_documentation"
    if p.startswith("trading_bot/tests/") or name.startswith("test_"):
        return "untracked_tests"
    if p.startswith("trading_bot/") and p.endswith(".py"):
        return "untracked_source_python"
    if p.startswith("tools/"):
        return "untracked_tooling"
    if name.startswith("requirements") and name.endswith(".txt"):
        return "untracked_dependency_manifest"
    if p.startswith("docs/") and p.endswith(".md"):
        return "untracked_project_documentation"
    return "untracked_other"


def summarize(rows: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for status, path in rows:
        buckets[_bucket(status, path)].append(path)
    return {key: sorted(values) for key, values in sorted(buckets.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Git working tree buckets.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--limit", type=int, default=12, help="Examples per bucket in text mode.")
    args = parser.parse_args()

    summary = summarize(_git_status())
    counts = {key: len(values) for key, values in summary.items()}

    if args.json:
        print(json.dumps({"counts": counts, "buckets": summary}, indent=2, sort_keys=True))
        return 0

    print("Working tree audit")
    print("==================")
    for key, count in counts.items():
        print(f"{key}: {count}")
        for path in summary[key][: args.limit]:
            print(f"  - {path}")
        remaining = count - args.limit
        if remaining > 0:
            print(f"  ... {remaining} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
