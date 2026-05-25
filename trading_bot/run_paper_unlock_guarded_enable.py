from __future__ import annotations

import json

from core.paper_unlock_guarded_enable import write_paper_unlock_guarded_enable_report


def main() -> None:
    report = write_paper_unlock_guarded_enable_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "enable_name": decision.get("enable_name"),
        "profile_name": decision.get("profile_name"),
        "selected_entries": decision.get("selected_entries"),
        "final_preflight_guard_ok": decision.get("final_preflight_guard_ok"),
        "operator_enable_suite_ok": decision.get("operator_enable_suite_ok"),
        "operator_controlled_enable_ok": decision.get("operator_controlled_enable_ok"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "manual_activation_allowed": report.get("manual_activation_allowed"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "automatic_activation_allowed": report.get("automatic_activation_allowed"),
        "orders_submitted": report.get("orders_submitted"),
        "positions_opened": report.get("positions_opened"),
        "report": (report.get("files") or {}).get("report", "data\\paper_unlock_guarded_enable_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_guarded_enable_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
