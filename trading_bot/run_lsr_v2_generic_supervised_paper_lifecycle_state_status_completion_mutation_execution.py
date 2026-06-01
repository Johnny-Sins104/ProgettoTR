from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution import (
    Settings,
    run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution,
)


def main() -> int:
    settings = Settings(project_root=Path(__file__).resolve().parents[1])
    report = run_generic_supervised_paper_lifecycle_state_status_completion_mutation_execution(settings)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
