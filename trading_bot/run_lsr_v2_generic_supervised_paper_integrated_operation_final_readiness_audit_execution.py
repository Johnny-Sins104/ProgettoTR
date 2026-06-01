from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_execution import (
    Settings,
    run_generic_supervised_paper_integrated_operation_final_readiness_audit_execution,
)


if __name__ == "__main__":
    payload = run_generic_supervised_paper_integrated_operation_final_readiness_audit_execution(
        Settings(project_root=Path(__file__).resolve().parents[1])
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
