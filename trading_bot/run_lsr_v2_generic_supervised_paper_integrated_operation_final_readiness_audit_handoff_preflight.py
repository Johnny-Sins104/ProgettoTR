from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_preflight import (
    run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_preflight,
)


def main() -> None:
    print(json.dumps(run_generic_supervised_paper_integrated_operation_final_readiness_audit_handoff_preflight(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
