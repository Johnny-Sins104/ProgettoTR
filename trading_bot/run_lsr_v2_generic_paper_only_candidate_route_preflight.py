from __future__ import annotations

import json

from core.lsr_v2_generic_paper_only_candidate_route_preflight import run_generic_paper_only_candidate_route_preflight


if __name__ == "__main__":
    print(json.dumps(run_generic_paper_only_candidate_route_preflight(), indent=2, sort_keys=True))
