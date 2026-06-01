from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.probability_compression_diagnostic import build_probability_compression_report


if __name__ == "__main__":
    print(json.dumps(build_probability_compression_report(), indent=2, sort_keys=True))
