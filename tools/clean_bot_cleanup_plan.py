from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _sample(paths: list[Path], limit: int = 20) -> list[str]:
    return [_rel(path) for path in sorted(paths)[:limit]]


def _glob(pattern: str) -> list[Path]:
    return [path for path in ROOT.glob(pattern) if path.is_file()]


def build_report() -> dict[str, Any]:
    data_dir = ROOT / "data"
    docs_dir = ROOT / "docs" / "patch_reports"
    trading_dir = ROOT / "trading_bot"
    cache_files = _glob("data/*_cache.parquet")
    active_state = [
        data_dir / "paper_state.json",
        data_dir / "paper_status.json",
        data_dir / "paper_events.jsonl",
        data_dir / "telegram_proactive_state.json",
        data_dir / "paper_position_monitor.json",
        data_dir / "clean_paper_state.json",
        data_dir / "clean_paper_events.jsonl",
    ]
    clean_core = sorted((ROOT / "trading_bot" / "clean_bot").glob("*.py"))
    clean_tools = [
        ROOT / "tools" / "clean_bot_backtest.py",
        ROOT / "tools" / "clean_bot_optimizer.py",
        ROOT / "tools" / "clean_bot_cleanup_plan.py",
        ROOT / "tools" / "clean_bot_paper_live.py",
    ]
    legacy_lsr_scripts = sorted(trading_dir.glob("run_lsr_v2_*.py"))
    legacy_unlock_scripts = sorted(trading_dir.glob("run_paper_unlock_*.py"))
    data_reports = sorted(
        path
        for path in data_dir.glob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".jsonl", ".csv", ".txt", ".html", ".log"}
        and path.name not in {item.name for item in active_state}
        and not path.name.startswith("clean_")
    )
    patch_reports = sorted(path for path in docs_dir.glob("*") if path.name != "PATCH_30_3_0V_MANIFEST.txt") if docs_dir.exists() else []
    root_temp_candidates = [
        path
        for path in (
            ROOT / "console_once_test.txt",
            ROOT / "console_once_pruning_test.txt",
            ROOT / "patch_reports.zip",
        )
        if path.exists()
    ]
    return {
        "report_type": "clean_bot_cleanup_plan",
        "diagnostic_only": True,
        "applies_deletions": False,
        "keep_now": {
            "launchers": [_rel(ROOT / "avvia_bot_live.bat"), _rel(ROOT / "trading_bot" / "avvia_bot_live.py")],
            "paper_runtime": [
                _rel(ROOT / "trading_bot" / "run_paper_trading.py"),
                _rel(ROOT / "trading_bot" / "core" / "paper_engine.py"),
                _rel(ROOT / "trading_bot" / "core" / "telegram_proactive.py"),
                _rel(ROOT / "trading_bot" / "core" / "telegram_control.py"),
            ],
            "clean_bot_core": _sample(clean_core, 50),
            "clean_bot_tools": _sample(clean_tools, 50),
            "market_caches": {"count": len(cache_files), "sample": _sample(cache_files, 20)},
            "active_state": [_rel(path) for path in active_state if path.exists()],
        },
        "archive_later_candidates": {
            "legacy_lsr_scripts": {"count": len(legacy_lsr_scripts), "sample": _sample(legacy_lsr_scripts, 25)},
            "legacy_paper_unlock_scripts": {"count": len(legacy_unlock_scripts), "sample": _sample(legacy_unlock_scripts, 25)},
            "historical_data_reports": {"count": len(data_reports), "sample": _sample(data_reports, 25)},
            "historical_patch_reports": {"count": len(patch_reports), "sample": _sample(patch_reports, 25)},
        },
        "delete_after_archive_candidates": {
            "root_temp_files": _sample(root_temp_candidates, 20),
            "rule": "Delete only after a zip/archive copy exists and clean bot paper runner is operational.",
        },
        "do_not_delete": [
            ".env",
            "data/*_cache.parquet",
            "data/paper_state.json",
            "data/paper_status.json",
            "data/paper_events.jsonl",
            "data/telegram_proactive_state.json",
            "data/paper_position_monitor.json",
            "data/clean_paper_state.json",
            "data/clean_paper_events.jsonl",
            "avvia_bot_live.bat",
            "trading_bot/avvia_bot_live.py",
            "trading_bot/clean_bot/",
        ],
        "next_cleanup_step": "Create archive/legacy_artifacts and move historical reports/scripts there only after the clean paper runner replaces the legacy paper strategy path.",
    }


def format_report(report: dict[str, Any]) -> str:
    keep = report["keep_now"]
    archive = report["archive_later_candidates"]
    delete = report["delete_after_archive_candidates"]
    return "\n".join(
        [
            "CLEAN BOT CLEANUP PLAN",
            "diagnostic_only=YES applies_deletions=NO",
            f"keep clean_core={len(keep['clean_bot_core'])} clean_tools={len(keep['clean_bot_tools'])} market_caches={keep['market_caches']['count']}",
            f"archive_later legacy_lsr_scripts={archive['legacy_lsr_scripts']['count']} legacy_unlock_scripts={archive['legacy_paper_unlock_scripts']['count']}",
            f"archive_later data_reports={archive['historical_data_reports']['count']} patch_reports={archive['historical_patch_reports']['count']}",
            f"delete_after_archive root_temp_files={len(delete['root_temp_files'])}",
            "do_not_delete=.env,data caches,paper state,current launcher,clean_bot",
            f"next={report['next_cleanup_step']}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a safe cleanup plan for the clean bot migration.")
    parser.add_argument("--output", default="data/clean_bot_cleanup_plan.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
