from __future__ import annotations

import json

try:
    from core.lsr_v2_launcher_runner_visibility_parity_audit import run_lsr_v2_launcher_runner_visibility_parity_audit
except Exception:  # pragma: no cover
    from trading_bot.core.lsr_v2_launcher_runner_visibility_parity_audit import run_lsr_v2_launcher_runner_visibility_parity_audit


if __name__ == "__main__":
    print(json.dumps(run_lsr_v2_launcher_runner_visibility_parity_audit(), indent=2, sort_keys=True))
