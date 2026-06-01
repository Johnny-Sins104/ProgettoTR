from __future__ import annotations

import json
from pathlib import Path

from core.lsr_v2_generic_supervised_paper_runtime_activation_envelope_preflight import (
    Settings,
    run_generic_supervised_paper_runtime_activation_envelope_preflight,
)


if __name__ == "__main__":
    payload = run_generic_supervised_paper_runtime_activation_envelope_preflight(
        Settings(project_root=Path(__file__).resolve().parents[1])
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
