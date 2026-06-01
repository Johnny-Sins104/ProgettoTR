from __future__ import annotations

import json

from core.lsr_v2_generic_paper_only_order_intent_materialization_dry_run import (
    run_generic_paper_only_order_intent_materialization_dry_run,
)


if __name__ == "__main__":
    print(json.dumps(run_generic_paper_only_order_intent_materialization_dry_run(), indent=2, sort_keys=True))
