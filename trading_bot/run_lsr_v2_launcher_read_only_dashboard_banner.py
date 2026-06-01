from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.lsr_v2_launcher_read_only_dashboard_banner import (  # noqa: E402
    build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files,
)


def main() -> int:
    report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir="data")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
