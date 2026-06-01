from __future__ import annotations

import json
from core.lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit import (
    run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit,
)

if __name__ == "__main__":
    print(json.dumps(run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(), indent=2, sort_keys=True))
