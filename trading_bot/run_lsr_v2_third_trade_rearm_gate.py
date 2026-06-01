"""CLI runner for Prompt 29.4.4s-10aj third-trade rearm gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_third_trade_rearm_gate import (  # noqa: E402
    LSRV2ThirdTradeRearmSettings,
    build_lsr_v2_third_trade_rearm_gate_report_from_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third paper-trade rearm gate")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    parser.add_argument("--no-write", action="store_true", help="Build report without writing JSON/JSONL outputs")
    args = parser.parse_args()

    settings = LSRV2ThirdTradeRearmSettings.from_env(data_dir=args.data_dir)
    report = build_lsr_v2_third_trade_rearm_gate_report_from_files(
        data_dir=args.data_dir,
        cycle_id=args.cycle_id,
        settings=settings,
        write_outputs=not args.no_write,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
