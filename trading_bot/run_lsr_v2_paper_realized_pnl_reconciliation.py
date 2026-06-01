from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_realized_pnl_reconciliation import build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_realized_pnl_reconciliation import build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 30.3.0F read-only paper realized PnL reconciliation and postmortem")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    bundle = build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(
        data_dir=args.data_dir,
        tolerance=args.tolerance,
    )
    pnl = bundle["pnl_report"]
    postmortem = bundle["postmortem_report"]
    print(json.dumps({
        "pnl_status": pnl.get("status"),
        "pnl_decision": pnl.get("decision"),
        "reconciliation_status": pnl.get("reconciliation_status"),
        "fee_accounting_mode": pnl.get("fee_accounting_mode"),
        "pnl_includes_fees": pnl.get("pnl_includes_fees"),
        "pnl_fee_inclusion_scope": pnl.get("pnl_fee_inclusion_scope"),
        "gross_pnl": pnl.get("gross_pnl"),
        "entry_fee": pnl.get("entry_fee"),
        "exit_fee": pnl.get("exit_fee"),
        "total_fees": pnl.get("total_fees"),
        "realized_pnl_recorded": pnl.get("realized_pnl_recorded"),
        "balance_delta": pnl.get("balance_delta"),
        "account_net_pnl_expected": pnl.get("account_net_pnl_expected"),
        "warnings": pnl.get("warnings"),
        "blockers": pnl.get("blockers"),
        "postmortem_status": postmortem.get("status"),
        "postmortem_decision": postmortem.get("decision"),
        "should_block_next_order_experimentation": postmortem.get("should_block_next_order_experimentation"),
        "recommendation": postmortem.get("recommendation"),
        "pnl_report": pnl.get("report"),
        "pnl_jsonl": pnl.get("jsonl"),
        "postmortem_report": postmortem.get("report"),
        "postmortem_jsonl": postmortem.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 1 if pnl.get("status") == "FAIL" or postmortem.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
