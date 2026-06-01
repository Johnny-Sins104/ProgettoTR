from __future__ import annotations

import json

from core.lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook import (
    run_generic_runtime_snapshot_footer_banner_wiring_hook,
)


def main() -> None:
    print(json.dumps(run_generic_runtime_snapshot_footer_banner_wiring_hook(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
