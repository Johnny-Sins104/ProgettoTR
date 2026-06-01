"""Paper-first launcher for Prompt 29.

The historical live loop in ``main.py`` remains available for research, but this
entrypoint refuses real-money execution.  It routes to the paper engine by
default and requires future explicit hardening before any live mode is allowed.

Prompt 29.4.4t-4 adds a read-only LSR-v2 dashboard/lifecycle banner before the
paper runner starts.  The banner reads already validated artifacts only; it does
not submit/close orders, mutate paper_state/paper_status, start schedulers, or
send Telegram messages.
"""
from __future__ import annotations

import sys

from run_paper_trading import main as paper_main

try:  # read-only launcher banner; fail closed if unavailable
    from core.lsr_v2_launcher_read_only_dashboard_banner import emit_lsr_v2_launcher_read_only_dashboard_banner
except Exception:  # pragma: no cover - launcher must remain usable if artifact module is absent
    emit_lsr_v2_launcher_read_only_dashboard_banner = None  # type: ignore[assignment]


def _live_requested(argv: list[str]) -> bool:
    return any(arg in {"--live", "--mode=live"} for arg in argv)


def _emit_lsr_v2_read_only_banner() -> None:
    if emit_lsr_v2_launcher_read_only_dashboard_banner is None:
        print("[LSR-V2 LAUNCHER DASHBOARD] unavailable read-only fail-closed")
        return
    try:
        emit_lsr_v2_launcher_read_only_dashboard_banner(data_dir="data")
    except Exception as exc:  # pragma: no cover - defensive; never change launcher execution mode
        print(f"[LSR-V2 LAUNCHER DASHBOARD] unavailable read-only fail-closed: {exc}")


def main() -> None:
    if _live_requested(sys.argv[1:]):
        raise SystemExit("Live real-money execution is disabled in Prompt 29. Use --mode paper.")
    _emit_lsr_v2_read_only_banner()
    paper_main()


if __name__ == "__main__":
    main()
