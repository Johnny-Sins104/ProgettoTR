from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_open_position_monitor_preflight import (
    run_generic_supervised_paper_open_position_monitor_preflight,
)


def main() -> int:
    report = run_generic_supervised_paper_open_position_monitor_preflight()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
