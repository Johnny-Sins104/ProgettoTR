"""Run the 29.4.4u-67 generic supervised paper integrated dry-run runtime bundle."""
from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_integrated_dry_run_runtime_bundle import (
    run_generic_supervised_paper_integrated_dry_run_runtime_bundle,
)


def main() -> int:
    report = run_generic_supervised_paper_integrated_dry_run_runtime_bundle()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
