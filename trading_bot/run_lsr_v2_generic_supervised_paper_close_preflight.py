from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_close_preflight import (
    run_generic_supervised_paper_close_preflight,
)


if __name__ == "__main__":
    print(json.dumps(run_generic_supervised_paper_close_preflight(), indent=2, sort_keys=True))
