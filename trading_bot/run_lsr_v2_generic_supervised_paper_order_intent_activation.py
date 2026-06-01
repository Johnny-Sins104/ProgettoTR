from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_order_intent_activation import (
    run_generic_supervised_paper_order_intent_activation,
)


def main() -> int:
    report = run_generic_supervised_paper_order_intent_activation()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
