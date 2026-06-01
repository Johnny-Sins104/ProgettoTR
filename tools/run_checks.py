"""Run repeatable local checks for ProgettoTR.

The default mode is dependency-aware but not dependency-blocking: it reports
missing optional test/runtime packages, parses Python files, and runs pytest only
when pytest is installed. Use ``--require-deps`` to fail on missing packages.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

BASE_DEPS = [
    "aiohttp",
    "ccxt",
    "numpy",
    "pandas",
    "pandas_ta",
    "plotly",
    "polars",
    "pyarrow",
    "requests",
    "sklearn",
    "xgboost",
]
DEV_DEPS = ["pytest", "pytest_asyncio"]

SMOKE_TESTS = [
    "trading_bot/test_runtime_risk_io_hardening.py",
    "trading_bot/test_paper_unlock_supervised_inactive_observation.py",
    "trading_bot/tests/test_paper_once_runner_footer_lsr_v2.py",
    "trading_bot/tests/test_lsr_v2_runtime_bridge_cycle_scoped.py",
]


def check_deps() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in BASE_DEPS + DEV_DEPS}


def iter_python_files() -> list[Path]:
    ignored_parts = {".git", "__pycache__", ".pytest_cache", "data"}
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in ignored_parts for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def check_syntax() -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for path in iter_python_files():
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except Exception as exc:
            errors.append({"path": str(path.relative_to(ROOT)), "error": repr(exc)})
    return errors


def run_pytest_smoke() -> int | None:
    if importlib.util.find_spec("pytest") is None:
        return None
    existing = [test for test in SMOKE_TESTS if (ROOT / test).exists()]
    if not existing:
        return 0
    env = os.environ.copy()
    pythonpath = [str(ROOT), str(ROOT / "trading_bot")]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    proc = subprocess.run([PYTHON, "-m", "pytest", *existing], cwd=ROOT, env=env)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ProgettoTR local checks.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary.")
    parser.add_argument("--no-pytest", action="store_true", help="Skip pytest smoke tests.")
    parser.add_argument("--require-deps", action="store_true", help="Fail when dependencies are missing.")
    args = parser.parse_args()

    deps = check_deps()
    missing = [name for name, present in deps.items() if not present]
    syntax_errors = check_syntax()
    pytest_code = None if args.no_pytest else run_pytest_smoke()
    if args.no_pytest:
        pytest_status: str | int = "skipped_by_flag"
    elif pytest_code is None:
        pytest_status = "skipped_missing_pytest"
    else:
        pytest_status = pytest_code

    summary = {
        "python": PYTHON,
        "dependency_count": len(deps),
        "missing_dependencies": missing,
        "syntax_checked_files": len(iter_python_files()),
        "syntax_errors": syntax_errors,
        "pytest_smoke": pytest_status,
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("Local checks")
        print("============")
        print(f"python={summary['python']}")
        print(f"syntax_checked_files={summary['syntax_checked_files']}")
        print(f"syntax_errors={len(syntax_errors)}")
        if missing:
            print("missing_dependencies=" + ",".join(missing))
        else:
            print("missing_dependencies=none")
        print(f"pytest_smoke={summary['pytest_smoke']}")
        for item in syntax_errors[:20]:
            print(f"syntax_error {item['path']}: {item['error']}")

    if syntax_errors:
        return 1
    if args.require_deps and missing:
        return 2
    if isinstance(pytest_code, int) and pytest_code != 0:
        return pytest_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
