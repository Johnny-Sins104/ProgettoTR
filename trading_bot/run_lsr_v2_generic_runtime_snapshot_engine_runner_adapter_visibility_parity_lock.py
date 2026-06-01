from __future__ import annotations

import json

from core.lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock import (
    run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock,
)


def main() -> None:
    report = run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
