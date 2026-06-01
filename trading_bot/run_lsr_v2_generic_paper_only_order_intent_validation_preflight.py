from __future__ import annotations

import json

from core.lsr_v2_generic_paper_only_order_intent_validation_preflight import (
    run_generic_paper_only_order_intent_validation_preflight,
)


if __name__ == "__main__":
    print(json.dumps(run_generic_paper_only_order_intent_validation_preflight(), indent=2, sort_keys=True))
