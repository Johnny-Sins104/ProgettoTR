from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.core.lsr_v2_two_trade_observation import run_two_trade_observation


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 two-trade postmortem observation / third-trade lock monitor")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--run-paper-cycles", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--duration-hours", type=float, default=0.0)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--cycle-timeout-seconds", type=int, default=900)
    report = run_two_trade_observation(
        data_dir=parser.parse_args().data_dir,
        run_paper_cycles=parser.parse_args().run_paper_cycles,
        max_cycles=parser.parse_args().max_cycles,
        duration_hours=parser.parse_args().duration_hours,
        interval_seconds=parser.parse_args().interval_seconds,
        cycle_timeout_seconds=parser.parse_args().cycle_timeout_seconds,
    )
    print(json.dumps({k: v for k, v in report.items() if k not in {"event_type", "prompt", "ts", "cycle_results"}}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
