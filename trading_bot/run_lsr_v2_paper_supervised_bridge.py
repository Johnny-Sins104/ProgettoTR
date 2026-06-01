from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.core.lsr_v2_paper_supervised_bridge import (  # noqa: E402
    LSRV2PaperSupervisedBridgeSettings,
    write_lsr_v2_paper_supervised_bridge_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LSR-v2 paper-supervised bridge scaffold / fail-closed runtime audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--operator-enable", action="store_true", help="Diagnostic operator flag only; does not enable submission")
    parser.add_argument("--operator-confirm", default="", help="Must match the confirmation phrase to produce would_route=true; still would_submit=false")
    parser.add_argument("--max-candidate-events", type=int, default=500)
    parser.add_argument("--no-emit-jsonl", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = LSRV2PaperSupervisedBridgeSettings.from_config()
    settings = LSRV2PaperSupervisedBridgeSettings(
        **{
            **settings.__dict__,
            "data_dir": str(args.data_dir),
            "operator_enable": bool(args.operator_enable),
            "operator_confirmation": str(args.operator_confirm or ""),
            "max_candidate_events": max(1, int(args.max_candidate_events)),
            "emit_bridge_events": not bool(args.no_emit_jsonl),
        }
    )
    report = write_lsr_v2_paper_supervised_bridge_report(args.data_dir, settings)
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "profile_name": report.get("profile_name"),
        "selected_overlay_id": report.get("selected_overlay_id"),
        "promotion_gate_pass": report.get("promotion_gate_pass"),
        "paper_supervised_candidate": report.get("paper_supervised_candidate"),
        "candidate_ready_events": report.get("candidate_ready_events"),
        "bridge_events": report.get("bridge_events"),
        "operator_enable": report.get("operator_enable"),
        "operator_confirmation_ok": report.get("operator_confirmation_ok"),
        "would_route_count": report.get("would_route_count"),
        "would_submit_count": report.get("would_submit_count"),
        "execution_enabled": report.get("execution_enabled"),
        "routing_enabled": report.get("routing_enabled"),
        "paper_order_submission_enabled": report.get("paper_order_submission_enabled"),
        "broker_submit_called": report.get("broker_submit_called"),
        "orders_submitted_by_lsr_v2_bridge": report.get("orders_submitted_by_lsr_v2_bridge"),
        "positions_opened_by_lsr_v2_bridge": report.get("positions_opened_by_lsr_v2_bridge"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "bridge_jsonl": report.get("bridge_jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
