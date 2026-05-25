from __future__ import annotations

import json

from core.paper_unlock_manual_switch_preflight import write_paper_unlock_manual_switch_preflight_report


def main() -> None:
    report = write_paper_unlock_manual_switch_preflight_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "preflight_name": decision.get("preflight_name"),
        "switch_name": decision.get("switch_name"),
        "profile_name": decision.get("profile_name"),
        "selected_entries": decision.get("selected_entries"),
        "switch_draft_ready": decision.get("switch_draft_ready"),
        "fail_closed_preflight_ok": decision.get("fail_closed_preflight_ok"),
        "future_patch_simulation_ok": decision.get("future_patch_simulation_ok"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "automatic_activation_allowed": report.get("automatic_activation_allowed"),
        "manual_activation_allowed": report.get("manual_activation_allowed"),
        "report": (report.get("files") or {}).get("report", "data\\paper_unlock_manual_switch_preflight_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_manual_switch_preflight_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
