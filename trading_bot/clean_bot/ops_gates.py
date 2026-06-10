"""
TR-OPS-01: Paper operations readiness gates.

Provides:
    no_live_modified(baseline_path, *, files=None, project_root=None)
        Compares current SHA-256 hashes against an explicit approved-baseline JSON.
        Detects changes that predate the current run — unlike the manifest-based
        check in run_phase_3_entry_preflight which only detects in-run mutations.

    worktree_normalization_audit(project_root=None)
        Read-only git status categorization: source, generated_artifacts,
        deletions, untracked. No file deletion, restoration, staging, commit
        or push is performed.

RUNTIME_BASELINE_FILES extends the original phase-3-preflight monitored list to
include runtime config (config.py), the market-data client (core/client.py), and
Telegram notification modules as required by TR-OPS-01.

No secret values are written to output or logs.
No live/testnet/exchange enablement.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Canonical list of runtime files checked by no_live_modified.
# TR-OPS-01 adds config, market-data client and Telegram modules to the
# original phase-3-preflight list (avvia_bot_live, paper_live, strategies,
# engine, paper_engine).
# ---------------------------------------------------------------------------

RUNTIME_BASELINE_FILES: list[str] = [
    "trading_bot/avvia_bot_live.py",
    "trading_bot/clean_bot/paper_live.py",
    "trading_bot/clean_bot/strategies.py",
    "trading_bot/core/engine.py",
    "trading_bot/core/paper_engine.py",
    # TR-OPS-01 additions
    "trading_bot/config.py",
    "trading_bot/core/client.py",
    "trading_bot/core/notifier.py",
    "trading_bot/core/telegram_control.py",
    "trading_bot/core/telegram_proactive.py",
    "trading_bot/core/lsr_v2_telegram_notification_bridge.py",
    "trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py",
    "trading_bot/core/lsr_v2_telegram_trade_dashboard.py",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    """Return SHA-256 hex of a file, or None if the file does not exist."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_GENERATED_ARTIFACT_SUFFIXES: frozenset[str] = frozenset({
    ".json", ".parquet", ".csv", ".jsonl",
    ".zip", ".log", ".txt", ".pkl", ".npy",
})


def _categorize_tracked_change(path: str) -> str:
    """Return 'source' or 'generated_artifact' for a tracked modified/added file."""
    p = Path(path)
    if any(part in ("data", "patch_reports", "__pycache__") for part in p.parts):
        return "generated_artifact"
    if p.suffix in _GENERATED_ARTIFACT_SUFFIXES:
        return "generated_artifact"
    return "source"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def no_live_modified(
    baseline_path: str | Path,
    *,
    files: list[str] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Compare current SHA-256 hashes against an explicit approved baseline.

    Unlike the manifest-based check that only detects in-run mutations,
    this function uses a persisted approved-baseline JSON so pre-existing
    modifications — changes that predate the current run — are detected.

    baseline_path:
        Path to a JSON file with structure
        ``{"approved_sha256": {"relative/path": "sha256hex", ...}}``.
    files:
        Relative paths to check (defaults to RUNTIME_BASELINE_FILES).
    project_root:
        Base directory for relative paths (defaults to project root).

    Returns a dict with:
        no_live_modified (bool), files_checked (int),
        issues (list[str]), file_results (dict).

    No secret values are included in the output.
    """
    check_files = files if files is not None else RUNTIME_BASELINE_FILES
    root = Path(project_root) if project_root is not None else _PROJECT_ROOT
    baseline_p = Path(baseline_path)

    if not baseline_p.exists():
        return {
            "no_live_modified": False,
            "files_checked": 0,
            "issues": [f"baseline not found: {baseline_p}"],
            "file_results": {},
        }

    try:
        baseline_data = json.loads(baseline_p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "no_live_modified": False,
            "files_checked": 0,
            "issues": [f"baseline unreadable: {exc}"],
            "file_results": {},
        }

    approved_hashes: dict[str, str | None] = baseline_data.get("approved_sha256", {})
    file_results: dict[str, Any] = {}
    issues: list[str] = []

    for rel in check_files:
        abs_path = root / rel
        current_hash = _sha256_file(abs_path)
        approved_hash = approved_hashes.get(rel)

        if current_hash is None:
            status = "MISSING"
            issues.append(f"{rel}: file does not exist")
        elif approved_hash is None:
            status = "NOT_IN_BASELINE"
            issues.append(f"{rel}: not in approved baseline")
        elif current_hash != approved_hash:
            status = "MODIFIED"
            issues.append(f"{rel}: hash differs from approved baseline")
        else:
            status = "UNCHANGED"

        file_results[rel] = {
            "approved_hash": approved_hash,
            "current_hash": current_hash,
            "status": status,
        }

    return {
        "no_live_modified": len(issues) == 0,
        "files_checked": len(check_files),
        "issues": issues,
        "file_results": file_results,
    }


def generate_approved_baseline(
    output_path: str | Path,
    *,
    files: list[str] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write an approved-baseline JSON from the current SHA-256 hashes.

    Call once after intentionally approving the current state of all monitored
    files.  The resulting file is then passed as baseline_path to no_live_modified().

    No secret values are read, written, or included in the output.
    """
    check_files = files if files is not None else RUNTIME_BASELINE_FILES
    root = Path(project_root) if project_root is not None else _PROJECT_ROOT
    output_p = Path(output_path)

    approved_sha256: dict[str, str | None] = {}
    missing: list[str] = []
    for rel in check_files:
        h = _sha256_file(root / rel)
        approved_sha256[rel] = h
        if h is None:
            missing.append(rel)

    baseline = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approved_sha256": approved_sha256,
        "files_count": len(check_files),
        "missing_files": missing,
    }
    output_p.parent.mkdir(parents=True, exist_ok=True)
    output_p.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "baseline_path": str(output_p),
        "files_registered": len(check_files) - len(missing),
        "missing_files": missing,
    }


def worktree_normalization_audit(
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Read-only working-tree normalization audit.

    Runs ``git status --porcelain=v1`` and partitions the output into:
    - source: modified/added Python or config source files tracked by git
    - generated_artifacts: modified/added data/report/output files tracked by git
    - deletions: tracked files deleted from the working tree
    - untracked: files not tracked by git (classified independently of type)

    Does NOT delete, restore, stage, commit, or push any file.
    Secret values are not read, written, or included in the output.
    """
    root = Path(project_root) if project_root is not None else _PROJECT_ROOT

    proc = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if proc.returncode != 0:
        return {
            "audit_status": "GIT_ERROR",
            "read_only": True,
            "error": proc.stderr.strip()[:200],
            "source": [],
            "generated_artifacts": [],
            "deletions": [],
            "untracked": [],
            "counts": {
                "source": 0, "generated_artifacts": 0,
                "deletions": 0, "untracked": 0,
            },
        }

    source: list[str] = []
    generated_artifacts: list[str] = []
    deletions: list[str] = []
    untracked: list[str] = []

    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path_raw = line[3:]
        # Renames are reported as "old -> new"; take only the destination path
        if " -> " in path_raw:
            path_raw = path_raw.split(" -> ", 1)[1]
        path = path_raw.strip()

        index_status = xy[0]
        work_status = xy[1]

        if index_status == "?" and work_status == "?":
            untracked.append(path)
        elif index_status == "D" or work_status == "D":
            deletions.append(path)
        else:
            cat = _categorize_tracked_change(path)
            if cat == "source":
                source.append(path)
            else:
                generated_artifacts.append(path)

    return {
        "audit_status": "OK",
        "read_only": True,
        "source": sorted(source),
        "generated_artifacts": sorted(generated_artifacts),
        "deletions": sorted(deletions),
        "untracked": sorted(untracked),
        "counts": {
            "source": len(source),
            "generated_artifacts": len(generated_artifacts),
            "deletions": len(deletions),
            "untracked": len(untracked),
        },
    }
