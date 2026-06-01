from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight import (
    Settings,
    run_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight,
)


def main() -> int:
    report = run_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight(
        Settings(project_root=Path("."))
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
