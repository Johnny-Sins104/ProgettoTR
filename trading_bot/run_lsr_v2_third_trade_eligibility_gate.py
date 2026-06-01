from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from trading_bot.core.lsr_v2_third_trade_eligibility_gate import (
        DEFAULT_MIN_4H_CYCLES,
        DEFAULT_MIN_8H_CYCLES,
        build_lsr_v2_third_trade_eligibility_gate_report_from_files,
    )
except Exception:  # pragma: no cover
    from core.lsr_v2_third_trade_eligibility_gate import (  # type: ignore
        DEFAULT_MIN_4H_CYCLES,
        DEFAULT_MIN_8H_CYCLES,
        build_lsr_v2_third_trade_eligibility_gate_report_from_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third supervised paper-trade eligibility gate")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--min-4h-cycles", type=int, default=DEFAULT_MIN_4H_CYCLES)
    parser.add_argument("--min-8h-cycles", type=int, default=DEFAULT_MIN_8H_CYCLES)
    args = parser.parse_args()
    report = build_lsr_v2_third_trade_eligibility_gate_report_from_files(
        data_dir=args.data_dir,
        min_4h_cycles=args.min_4h_cycles,
        min_8h_cycles=args.min_8h_cycles,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
