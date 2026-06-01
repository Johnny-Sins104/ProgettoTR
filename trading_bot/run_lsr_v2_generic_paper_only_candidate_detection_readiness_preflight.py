from __future__ import annotations

import json

from core.lsr_v2_generic_paper_only_candidate_detection_readiness_preflight import (
    run_generic_paper_only_candidate_detection_readiness_preflight,
)


def main() -> None:
    report = run_generic_paper_only_candidate_detection_readiness_preflight()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
