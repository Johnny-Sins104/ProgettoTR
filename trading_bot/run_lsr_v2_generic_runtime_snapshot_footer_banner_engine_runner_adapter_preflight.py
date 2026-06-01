from __future__ import annotations

import json

from core.lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight import (
    run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight,
)


def main() -> None:
    print(json.dumps(run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
