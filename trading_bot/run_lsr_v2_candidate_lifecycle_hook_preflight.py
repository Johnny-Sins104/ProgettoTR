from __future__ import annotations

import json

try:
    from core.lsr_v2_candidate_lifecycle_hook_preflight import run_lsr_v2_candidate_lifecycle_hook_preflight
except Exception:  # pragma: no cover
    from trading_bot.core.lsr_v2_candidate_lifecycle_hook_preflight import run_lsr_v2_candidate_lifecycle_hook_preflight


if __name__ == "__main__":
    print(json.dumps(run_lsr_v2_candidate_lifecycle_hook_preflight(), indent=2, sort_keys=True))
