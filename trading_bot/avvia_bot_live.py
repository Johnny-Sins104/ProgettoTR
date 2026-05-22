"""Paper-first launcher for Prompt 29.

The historical live loop in ``main.py`` remains available for research, but this
entrypoint refuses real-money execution.  It routes to the new paper engine by
default and requires future explicit hardening before any live mode is allowed.
"""
from __future__ import annotations

import sys

from run_paper_trading import main as paper_main


if __name__ == "__main__":
    if any(arg in {"--live", "--mode=live"} for arg in sys.argv[1:]):
        raise SystemExit("Live real-money execution is disabled in Prompt 29. Use --mode paper.")
    paper_main()
