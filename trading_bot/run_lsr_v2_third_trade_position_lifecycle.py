from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from trading_bot.core.lsr_v2_third_trade_position_lifecycle import build_lsr_v2_third_trade_position_lifecycle_report_from_files
except Exception:  # pragma: no cover
    from core.lsr_v2_third_trade_position_lifecycle import build_lsr_v2_third_trade_position_lifecycle_report_from_files  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third paper trade position lifecycle audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(
        data_dir=args.data_dir,
        requested_cycle_id=args.cycle_id,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
