from __future__ import annotations

import json

from core.lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution import (
    run_generic_supervised_paper_runtime_activation_envelope_execution,
)


if __name__ == "__main__":
    print(json.dumps(run_generic_supervised_paper_runtime_activation_envelope_execution(), indent=2, sort_keys=True))
