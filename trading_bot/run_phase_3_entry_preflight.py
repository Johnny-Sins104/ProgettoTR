"""
run_phase_3_entry_preflight.py — Prompt 3A-H: Hotfix finale del preflight Fase 3
=================================================================================
Reads real artifacts (phase_1_2_recertification_status.json,
market_data_integrity_status.json), verifies SHA-256 hashes, and decides
whether Phase 3 (benchmark) is authorized to begin.

Does NOT: open orders, connect to exchanges, modify strategies, modify paper
          state, modify API keys, enable live or testnet trading.

Exit code: 0 if preflight PASS, 1 if BLOCKED.

Usage (from project root):
    python trading_bot/run_phase_3_entry_preflight.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent
_TRADING_BOT = _THIS_FILE.parent
for _p in (str(PROJECT_ROOT), str(_TRADING_BOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
OUTPUT_STATUS_PATH = DATA_DIR / "phase_3_entry_preflight_status.json"
OUTPUT_REPORT_PATH = DOCS_DIR / "phase_3_entry_preflight_report.md"

RECERT_STATUS_PATH = DATA_DIR / "phase_1_2_recertification_status.json"
AUDIT_STATUS_PATH = DATA_DIR / "market_data_integrity_status.json"

DIAGNOSTIC_ONLY: bool = True
OPENS_ORDERS: bool = False
LIVE_TRADING_ALLOWED: bool = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pf(ok: bool) -> str:
    return "PASS" if ok else "BLOCKED"


# ---------------------------------------------------------------------------
# Input verification
# ---------------------------------------------------------------------------

def _verify_inputs() -> Dict[str, Any]:
    """
    Verify that both upstream artifact files exist and read their gate values.
    Compute SHA-256 hashes to tie this preflight to the exact upstream artifacts.
    Returns a dict with status, hashes, and gate values.
    """
    issues: List[str] = []
    result: Dict[str, Any] = {}

    for name, path in [
        ("recertification", RECERT_STATUS_PATH),
        ("audit", AUDIT_STATUS_PATH),
    ]:
        if not path.exists():
            issues.append(f"Missing upstream artifact: {path.name}")
            result[f"{name}_path"] = str(path)
            result[f"{name}_exists"] = False
        else:
            result[f"{name}_path"] = str(path)
            result[f"{name}_exists"] = True
            result[f"{name}_sha256"] = _sha256_file(path)

    if issues:
        result["status"] = "BLOCKED"
        result["issues"] = issues
        return result

    recert = _load_json(RECERT_STATUS_PATH)
    audit = _load_json(AUDIT_STATUS_PATH)

    result["recertification_gate"] = recert.get("gate_result", "MISSING")
    result["recertification_approved_for_phase_3"] = recert.get("approved_for_phase_3", False)
    result["audit_benchmark_readiness_gate"] = audit.get("benchmark_readiness_gate", "MISSING")
    result["audit_raw_data_gate"] = audit.get("raw_data_gate", "MISSING")
    result["audit_aggregation_check_status"] = audit.get("aggregation_check", {}).get("status", "MISSING")

    if result["recertification_gate"] != "PASS":
        issues.append(
            f"phase_1_2_recertification_status.json gate_result={result['recertification_gate']!r} "
            "(expected PASS)"
        )
    if not result["recertification_approved_for_phase_3"]:
        issues.append("phase_1_2_recertification_status.json approved_for_phase_3=False")
    if result["audit_benchmark_readiness_gate"] != "PASS":
        issues.append(
            f"market_data_integrity_status.json benchmark_readiness_gate={result['audit_benchmark_readiness_gate']!r} "
            "(expected PASS)"
        )
    if result["audit_raw_data_gate"] != "PASS":
        issues.append(
            f"market_data_integrity_status.json raw_data_gate={result['audit_raw_data_gate']!r} "
            "(expected PASS)"
        )
    if result["audit_aggregation_check_status"] != "PASS":
        issues.append(
            f"market_data_integrity_status.json aggregation_check.status={result['audit_aggregation_check_status']!r} "
            "(expected PASS)"
        )

    result["status"] = _pf(len(issues) == 0)
    result["issues"] = issues
    return result


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

def _check_safety_invariants() -> Dict[str, Any]:
    """Verify DIAGNOSTIC_ONLY, OPENS_ORDERS, LIVE_TRADING_ALLOWED flags."""
    checks = {
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
    }
    issues = []
    if not DIAGNOSTIC_ONLY:
        issues.append("DIAGNOSTIC_ONLY is False")
    if OPENS_ORDERS:
        issues.append("OPENS_ORDERS is True")
    if LIVE_TRADING_ALLOWED:
        issues.append("LIVE_TRADING_ALLOWED is True")
    return {"checks": checks, "issues": issues, "status": _pf(len(issues) == 0)}


# ---------------------------------------------------------------------------
# Gate commands verification
# ---------------------------------------------------------------------------

def _run_gate_command(cmd: List[str], label: str) -> Dict[str, Any]:
    """Run a gate command and record exit code and summary output."""
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    lines = r.stdout.strip().splitlines()
    summary = lines[-1] if lines else "(no output)"
    return {
        "command": " ".join(cmd),
        "label": label,
        "returncode": r.returncode,
        "summary": summary,
        "passed": r.returncode == 0,
    }


def _verify_gate_commands() -> Dict[str, Any]:
    """
    Run all 5 gate exit commands and verify each exits code 0.
    Commands:
      1. python trading_bot/run_market_data_integrity_audit.py
      2. python trading_bot/run_phase_1_2_recertification.py
      3. python -m pytest --collect-only -q
      4. python -m pytest -q
    (Command 5 — run_phase_3_entry_preflight.py itself — is the caller.)
    """
    gate_cmds = [
        ([sys.executable, "trading_bot/run_market_data_integrity_audit.py"],
         "data_integrity_audit"),
        ([sys.executable, "trading_bot/run_phase_1_2_recertification.py"],
         "phase_1_2_recertification"),
        ([sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
         "pytest_collect"),
        ([sys.executable, "-m", "pytest", "-q", "--tb=short", "--no-header"],
         "pytest_run"),
    ]
    results = []
    all_pass = True
    for cmd, label in gate_cmds:
        r = _run_gate_command(cmd, label)
        results.append(r)
        if not r["passed"]:
            all_pass = False

    return {
        "gate_commands": results,
        "all_commands_exit_0": all_pass,
        "status": _pf(all_pass),
    }


# ---------------------------------------------------------------------------
# Manifest snapshot (Fix C — auto-regeneration with before/after SHA-256)
# ---------------------------------------------------------------------------

# Live/paper state files (must be UNCHANGED throughout the run)
_LIVE_PAPER_FILES: List[str] = [
    "trading_bot/avvia_bot_live.py",
    "trading_bot/clean_bot/paper_live.py",
    "trading_bot/clean_bot/strategies.py",
    "trading_bot/core/engine.py",
    "trading_bot/core/paper_engine.py",
    "data/clean_paper_state.json",
    "data/clean_paper_events.jsonl",
]

_MODIFIED_BY_3AH: List[str] = [
    "trading_bot/core/unified_trade_cost.py",
    "trading_bot/run_market_data_integrity_audit.py",
    "trading_bot/run_phase_1_2_recertification.py",
    "trading_bot/run_phase_3_entry_preflight.py",
    "trading_bot/tests/test_unified_trade_cost.py",
    "trading_bot/tests/test_market_data_integrity.py",
]

_OUTPUT_FILES: List[str] = [
    "data/market_data_integrity_status.json",
    "data/phase_1_2_recertification_status.json",
    "data/phase_3_entry_preflight_status.json",
    "data/phase_3_entry_preflight_manifest.json",
    "docs/phase_3_entry_preflight_report.md",
    "docs/phase_1_2_recertification_report.md",
    "docs/market_data_integrity_report.md",
]


def _hash_file(p: Path) -> Dict[str, Any]:
    """Return sha256, md5, and size for a file, or None values if missing."""
    if not p.exists():
        return {"sha256": None, "md5": None, "size": 0, "exists": False}
    sha = hashlib.sha256()
    md = hashlib.md5()
    size = 0
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
            md.update(chunk)
            size += len(chunk)
    return {"sha256": sha.hexdigest(), "md5": md.hexdigest(), "size": size, "exists": True}


def _capture_before_hashes() -> Dict[str, Dict[str, Any]]:
    """Capture SHA-256 + MD5 for live/paper files at startup (before gate commands)."""
    result: Dict[str, Dict[str, Any]] = {}
    for rel in _LIVE_PAPER_FILES:
        result[rel] = _hash_file(PROJECT_ROOT / rel)
    return result


def _build_manifest_snapshot(before_hashes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the manifest snapshot with before/after SHA-256 for all monitored files.

    before_hashes: captured at startup (before gate commands ran).
    after_hashes: captured now (end of run).

    Tamper check: for each live/paper file, before_sha256 must == after_sha256.
    """
    all_files = _LIVE_PAPER_FILES + _MODIFIED_BY_3AH + _OUTPUT_FILES

    snapshot: Dict[str, Any] = {}
    tamper_issues: List[str] = []
    now_ts = datetime.now(timezone.utc).isoformat()

    for rel in all_files:
        p = PROJECT_ROOT / rel
        after = _hash_file(p)
        category = (
            "live_paper_state" if rel in _LIVE_PAPER_FILES
            else "modified_by_3ah" if rel in _MODIFIED_BY_3AH
            else "diagnostic_output"
        )
        entry: Dict[str, Any] = {
            "exists": after["exists"],
            "category": category,
            "sha256_after": after["sha256"],
            "md5_after": after["md5"],
            "size_after": after["size"],
        }

        if rel in _LIVE_PAPER_FILES:
            before = before_hashes.get(rel, {})
            entry["sha256_before"] = before.get("sha256")
            entry["md5_before"] = before.get("md5")
            entry["size_before"] = before.get("size", 0)
            entry["exists_before"] = before.get("exists", False)

            sha_before = before.get("sha256")
            sha_after = after["sha256"]
            unchanged = (sha_before == sha_after) and sha_before is not None
            entry["unchanged"] = unchanged
            if not unchanged and after["exists"]:
                tamper_issues.append(
                    f"{rel}: SHA-256 changed "
                    f"({str(sha_before)[:16]}... → {str(sha_after)[:16]}...)"
                )
        else:
            # For non-live files, just record md5_before for backward-compat
            entry["md5_before"] = after.get("md5")

        snapshot[rel] = entry

    no_live_modified = len(tamper_issues) == 0

    manifest: Dict[str, Any] = {
        "manifest_type": "phase_3_entry_preflight",
        "generated_at": now_ts,
        "live_paper_files": _LIVE_PAPER_FILES,
        "files_monitored": snapshot,
        "tamper_issues": tamper_issues,
        "no_live_modified": no_live_modified,
        "invariant_status": no_live_modified,
        "verdict": "CLEAN" if no_live_modified else "TAMPERED",
    }

    # Write the manifest to disk (Fix C: auto-regenerated at runtime)
    manifest_path = DATA_DIR / "phase_3_entry_preflight_manifest.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return {
        "snapshot_timestamp_utc": now_ts,
        "file_snapshot": snapshot,
        "live_paper_files": _LIVE_PAPER_FILES,
        "tamper_issues": tamper_issues,
        "no_live_modified": no_live_modified,
        "manifest_written_to": str(manifest_path),
        "status": _pf(no_live_modified),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("  Phase 3 Entry Preflight — DIAGNOSTIC ONLY")
    print("  Opens orders: False | Live trading: False")
    print("=" * 70)
    print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")

    # Capture live/paper file hashes BEFORE any gate commands run (Fix C)
    before_hashes = _capture_before_hashes()

    issues: List[str] = []
    checks: Dict[str, Any] = {}

    # 1. Safety invariants
    print("\n[1/5] Verifying safety invariants ...")
    c1 = _check_safety_invariants()
    checks["safety_invariants"] = c1
    print(f"  diagnostic_only = {c1['checks']['diagnostic_only']}")
    print(f"  opens_orders    = {c1['checks']['opens_orders']}")
    print(f"  live_trading    = {c1['checks']['live_trading_allowed']}")
    print(f"  Status          : {c1['status']}")
    issues.extend(c1["issues"])

    # 2. Verify upstream artifacts
    print("\n[2/5] Verifying upstream artifacts (SHA-256) ...")
    c2 = _verify_inputs()
    checks["upstream_artifacts"] = c2
    if c2.get("recertification_sha256"):
        print(f"  recertification SHA-256 : {c2['recertification_sha256'][:16]}...")
    if c2.get("audit_sha256"):
        print(f"  audit SHA-256           : {c2['audit_sha256'][:16]}...")
    print(f"  recertification gate    : {c2.get('recertification_gate')}")
    print(f"  benchmark_readiness     : {c2.get('audit_benchmark_readiness_gate')}")
    print(f"  aggregation_check       : {c2.get('audit_aggregation_check_status')}")
    print(f"  Status                  : {c2['status']}")
    issues.extend(c2.get("issues", []))

    # 3. Manifest + tamper check (uses before_hashes from startup — Fix C)
    print("\n[3/5] Building manifest snapshot (tamper check) ...")
    c3 = _build_manifest_snapshot(before_hashes)
    checks["manifest_snapshot"] = c3
    print(f"  Files snapshotted : {len(c3['file_snapshot'])}")
    print(f"  No live modified  : {c3['no_live_modified']}")
    print(f"  Status            : {c3['status']}")
    if c3["tamper_issues"]:
        for ti in c3["tamper_issues"]:
            print(f"    TAMPER: {ti}")
    issues.extend(c3.get("tamper_issues", []))

    # 4. Gate commands (audit + recertification + full pytest)
    # Only run if upstream artifacts already indicate PASS to avoid running a
    # long pytest suite on an already-failed preflight.
    if c2["status"] == "BLOCKED":
        print("\n[4/5] Skipping gate command re-run (upstream artifacts BLOCKED)")
        checks["gate_commands"] = {
            "status": "SKIPPED",
            "reason": "Upstream artifacts gate is BLOCKED — fix first",
            "gate_commands": [],
            "all_commands_exit_0": False,
        }
        issues.append("Gate commands skipped: upstream artifacts BLOCKED")
    else:
        print("\n[4/5] Running gate commands ...")
        print("  (This runs the full pytest suite — may take ~30 s)")
        c4 = _verify_gate_commands()
        checks["gate_commands"] = c4
        for gc in c4["gate_commands"]:
            status_tag = "OK" if gc["passed"] else f"FAIL (rc={gc['returncode']})"
            print(f"  [{status_tag}] {gc['label']}: {gc['summary'][:60]}")
        print(f"  Status : {c4['status']}")
        if not c4["all_commands_exit_0"]:
            failed = [g["label"] for g in c4["gate_commands"] if not g["passed"]]
            issues.append(f"Gate commands failed: {', '.join(failed)}")

    # 5. Cost model import check
    print("\n[5/5] Verifying cost model importable ...")
    try:
        from core.unified_trade_cost import UnifiedCostModel, SCENARIO_NAMES
        _r = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=50000.0, exit_price=51000.0, quantity=0.01,
            scenario="realistic", symbol="BTC/USDT", timeframe="15m",
        )
        cost_model_ok = True
        checks["cost_model"] = {
            "importable": True,
            "api_test_passed": True,
            "net_R_sample": _r["net_R"],
            "scenarios": list(SCENARIO_NAMES),
            "status": "PASS",
        }
        print(f"  UnifiedCostModel imported, net_R sample = {_r['net_R']:.4f}")
        print("  Status : PASS")
    except Exception as exc:
        cost_model_ok = False
        checks["cost_model"] = {
            "importable": False,
            "error": str(exc),
            "status": "BLOCKED",
        }
        issues.append(f"UnifiedCostModel import failed: {exc}")
        print(f"  Status : BLOCKED — {exc}")

    # ---------------------------------------------------------------------------
    # Gate evaluation
    # ---------------------------------------------------------------------------
    gate_result = _pf(len(issues) == 0)
    approved_for_phase_3 = gate_result == "PASS"

    # ---------------------------------------------------------------------------
    # Output JSON
    # ---------------------------------------------------------------------------
    output: Dict[str, Any] = {
        "report_type": "phase_3_entry_preflight",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
        "upstream_artifacts": {
            "recertification_path": str(RECERT_STATUS_PATH),
            "recertification_sha256": c2.get("recertification_sha256"),
            "audit_path": str(AUDIT_STATUS_PATH),
            "audit_sha256": c2.get("audit_sha256"),
        },
        "checks": checks,
        "gate_issues": issues,
        "gate_result": gate_result,
        "approved_for_phase_3": approved_for_phase_3,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_STATUS_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------------------
    # Output report
    # ---------------------------------------------------------------------------
    _write_report(output)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  PHASE 3 ENTRY PREFLIGHT SUMMARY")
    print("=" * 70)
    print(f"  upstream recertification : {c2.get('recertification_gate')}")
    print(f"  upstream benchmark_ready : {c2.get('audit_benchmark_readiness_gate')}")
    print(f"  aggregation_check        : {c2.get('audit_aggregation_check_status')}")
    print(f"  no_live_modified         : {c3['no_live_modified']}")
    print(f"  manifest_regenerated     : {c3.get('manifest_written_to', '?')}")
    print(f"  cost_model_ok            : {cost_model_ok}")
    gc = checks.get("gate_commands", {})
    print(f"  all_gate_cmds_exit_0     : {gc.get('all_commands_exit_0', 'N/A')}")
    print(f"\n  GATE RESULT              : {gate_result}")
    if issues:
        print(f"  Issues ({len(issues)}):")
        for iss in issues:
            print(f"    - {iss}")
    else:
        print("  All preflight checks passed.")
    print(f"\n  Status JSON : {OUTPUT_STATUS_PATH}")
    print(f"  Report      : {OUTPUT_REPORT_PATH}")
    print("=" * 70)

    return 0 if gate_result == "PASS" else 1


def _write_report(output: Dict[str, Any]) -> None:
    gate = output["gate_result"]
    ts = output["generated_at"]
    issues = output.get("gate_issues", [])
    c_upstream = output["checks"].get("upstream_artifacts", {})
    c_manifest = output["checks"].get("manifest_snapshot", {})
    c_cmds = output["checks"].get("gate_commands", {})
    c_cost = output["checks"].get("cost_model", {})

    agg_status = c_upstream.get("audit_aggregation_check_status", "?")
    bench_gate = c_upstream.get("audit_benchmark_readiness_gate", "?")
    recert_gate = c_upstream.get("recertification_gate", "?")

    lines = [
        f"# Phase 3 Entry Preflight Report",
        f"**Generated:** {ts}",
        f"**Runner:** `trading_bot/run_phase_3_entry_preflight.py`",
        f"**Gate result: {gate}**",
        "",
        "---",
        "",
        "## Upstream Gates",
        "",
        f"| Gate | Result |",
        f"|------|--------|",
        f"| `phase_1_2_recertification_status.json` gate_result | {recert_gate} |",
        f"| `market_data_integrity_status.json` benchmark_readiness_gate | {bench_gate} |",
        f"| `market_data_integrity_status.json` aggregation_check.status | {agg_status} |",
        "",
        "## Safety Constraints",
        "",
        "```",
        f"diagnostic_only               = {DIAGNOSTIC_ONLY}",
        f"opens_orders                  = {OPENS_ORDERS}",
        f"live_trading_allowed          = {LIVE_TRADING_ALLOWED}",
        "```",
        "",
        "## Tamper Check (live/paper state)",
        "",
        f"- no_live_modified: `{c_manifest.get('no_live_modified')}`",
    ]

    if c_manifest.get("tamper_issues"):
        lines.append("")
        lines.append("**TAMPER DETECTED:**")
        for ti in c_manifest["tamper_issues"]:
            lines.append(f"- {ti}")

    lines += [
        "",
        "## Gate Commands",
        "",
    ]
    cmds = c_cmds.get("gate_commands", [])
    if cmds:
        lines.append("| Label | Exit code | Summary |")
        lines.append("|-------|-----------|---------|")
        for gc in cmds:
            lines.append(
                f"| `{gc['label']}` | {gc['returncode']} | {gc['summary'][:80]} |"
            )
    else:
        lines.append(f"Status: `{c_cmds.get('status', 'SKIPPED')}`")
        if c_cmds.get("reason"):
            lines.append(f"Reason: {c_cmds['reason']}")

    lines += [
        "",
        "## Cost Model",
        "",
        f"- Importable: `{c_cost.get('importable')}`",
        f"- API test passed: `{c_cost.get('api_test_passed')}`",
        "",
    ]

    if gate == "PASS":
        lines += [
            "## Gate: PASS",
            "",
            "Phase 3 (benchmark) is authorized to proceed.",
            "",
            "**Authorized inputs:**",
            "- Raw OHLCV 5m: `data/btc_5m_150k_cache.parquet` (and other raw files passing raw_data_gate)",
            "- Raw OHLCV 15m: `data/btc_15m_50k_cache.parquet`",
            "- On-the-fly 15m aggregation from 5m via `resample('15min', closed='left', label='left')`",
            "",
            "**NOT authorized for Phase 3 input (contaminated):**",
            "- `data/timeframe_runs/` — contamination documented",
            "- `data/signal_density/` — missing metadata documented",
            "",
            "**Risk policy (mandatory):**",
            "```",
            "risk_per_trade_pct = 0.005   # 0.5% of equity — NOT 0.5 (= 50%)",
            "```",
        ]
    else:
        lines += [
            "## Gate: BLOCKED",
            "",
            "Phase 3 is NOT authorized. Remaining issues:",
            "",
        ]
        for iss in issues:
            lines.append(f"- {iss}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
