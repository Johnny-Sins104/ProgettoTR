from __future__ import annotations

import json

from core.paper_unlock_final_enable_preflight import write_paper_unlock_final_enable_preflight_report


def main() -> None:
    report = write_paper_unlock_final_enable_preflight_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "final_preflight_name": decision.get("final_preflight_name"),
        "activation_patch_name": decision.get("activation_patch_name"),
        "profile_name": decision.get("profile_name"),
        "selected_entries": decision.get("selected_entries"),
        "activation_patch_guard_ok": decision.get("activation_patch_guard_ok"),
        "final_enable_preflight_ok": decision.get("final_enable_preflight_ok"),
        "paper_order_activation_candidate_ok": decision.get("paper_order_activation_candidate_ok"),
        "paper_order_activation_candidate_allowed": decision.get("paper_order_activation_candidate_allowed"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "automatic_activation_allowed": report.get("automatic_activation_allowed"),
        "manual_activation_allowed": report.get("manual_activation_allowed"),
        "report": (report.get("files") or {}).get("report", "data\\paper_unlock_final_enable_preflight_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_final_enable_preflight_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
