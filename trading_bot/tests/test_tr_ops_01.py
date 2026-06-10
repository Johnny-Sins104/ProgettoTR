"""
TR-OPS-01 — Paper operations readiness gates tests.

Verifies:
  - Clean paper runner loads project .env without logging secrets.
  - no_live_modified detects pre-existing changes (not just in-run changes).
  - no_live_modified covers runtime config, market-data client and Telegram modules.
  - worktree_normalization_audit is read-only (git status only, no mutations).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# test_clean_runner_loads_dotenv_without_logging_secrets
# ---------------------------------------------------------------------------

def test_clean_runner_loads_dotenv_without_logging_secrets(tmp_path, monkeypatch):
    """paper_live.load_paper_env(dotenv_path=...) must read vars from .env
    without ever exposing the secret value in return values or formatted output."""
    from trading_bot.clean_bot.paper_live import (
        CleanPaperSettings,
        _send_telegram,
        format_cycle,
        load_paper_env,
    )

    # A fake secret that must never appear in logs or return values
    secret_value = "TR_OPS_TEST_TOKEN_MUST_NOT_APPEAR_IN_OUTPUT"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"TELEGRAM_TOKEN={secret_value}\n"
        "# TR-OPS-01 test env — no real secrets\n",
        encoding="utf-8",
    )

    # Clear env vars so they come only from the test .env
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Load .env from the explicit test path
    loaded = load_paper_env(dotenv_path=str(env_file))
    assert loaded is True, "load_paper_env must return True when python-dotenv is available"
    assert os.getenv("TELEGRAM_TOKEN") == secret_value, (
        "TELEGRAM_TOKEN must be readable via os.getenv after load_paper_env"
    )

    # _send_telegram return dict must not contain the secret
    settings = CleanPaperSettings(telegram_enabled=True)
    result = _send_telegram(settings, "test_probe_message")
    result_str = json.dumps(result, sort_keys=True)
    assert secret_value not in result_str, (
        f"Secret value must not appear in _send_telegram return: {result_str}"
    )
    # With TELEGRAM_TOKEN set but TELEGRAM_CHAT_ID absent, the only valid reasons are:
    assert result.get("reason") in (
        "missing_TELEGRAM_TOKEN_or_TELEGRAM_CHAT_ID",
        "placeholder_telegram_values",
        "telegram_disabled",
    ), f"Unexpected _send_telegram reason: {result.get('reason')!r}"

    # format_cycle output must not contain the secret
    cycle_output = format_cycle({
        "action": "HOLD",
        "symbol": "XRP/USDT",
        "bar_time": "2026-01-01T00:00:00+00:00",
        "source": "cache",
        "last": 0.5,
        "equity": 100.0,
        "cash": 100.0,
        "position_open": False,
        "signal": None,
    })
    assert secret_value not in cycle_output, (
        "Secret value must not appear in format_cycle output"
    )


# ---------------------------------------------------------------------------
# test_no_live_modified_detects_preexisting_runtime_changes
# ---------------------------------------------------------------------------

def test_no_live_modified_detects_preexisting_runtime_changes(tmp_path):
    """no_live_modified must detect a change that existed BEFORE the check ran,
    not only changes made during the run.

    This is the key difference from the manifest-based check in
    run_phase_3_entry_preflight, which only captures before/after during a single run.
    """
    from trading_bot.clean_bot.ops_gates import no_live_modified

    # Create a fake monitored file and record its approved hash
    sub = tmp_path / "sub"
    sub.mkdir()
    src = sub / "module.py"
    src.write_text("# original content", encoding="utf-8")
    approved_hash = hashlib.sha256(src.read_bytes()).hexdigest()

    baseline = {"approved_sha256": {"sub/module.py": approved_hash}}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    # Modify the file BEFORE calling no_live_modified — this is a pre-existing change
    src.write_text("# modified content — preexisting change", encoding="utf-8")

    result = no_live_modified(
        baseline_path,
        files=["sub/module.py"],
        project_root=tmp_path,
    )

    assert result["no_live_modified"] is False, (
        "no_live_modified must be False when a file was modified before the check"
    )
    assert len(result["issues"]) >= 1, "Expected at least one issue"
    assert any("sub/module.py" in iss for iss in result["issues"]), (
        f"Expected an issue mentioning 'sub/module.py', got: {result['issues']}"
    )
    assert result["file_results"]["sub/module.py"]["status"] == "MODIFIED", (
        f"Expected status MODIFIED, got: {result['file_results']['sub/module.py']['status']}"
    )


# ---------------------------------------------------------------------------
# test_no_live_modified_covers_runtime_files
# ---------------------------------------------------------------------------

def test_no_live_modified_covers_runtime_files():
    """RUNTIME_BASELINE_FILES must include runtime config (config.py),
    market-data client (core/client.py), and all three lsr_v2 Telegram bridge modules."""
    from trading_bot.clean_bot.ops_gates import RUNTIME_BASELINE_FILES

    assert "trading_bot/config.py" in RUNTIME_BASELINE_FILES, (
        "RUNTIME_BASELINE_FILES must include trading_bot/config.py (runtime config)"
    )
    assert "trading_bot/core/client.py" in RUNTIME_BASELINE_FILES, (
        "RUNTIME_BASELINE_FILES must include trading_bot/core/client.py (market-data client)"
    )
    required_telegram = [
        "trading_bot/core/lsr_v2_telegram_notification_bridge.py",
        "trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py",
        "trading_bot/core/lsr_v2_telegram_trade_dashboard.py",
        "trading_bot/core/notifier.py",
        "trading_bot/core/telegram_proactive.py",
    ]
    for tg in required_telegram:
        assert tg in RUNTIME_BASELINE_FILES, (
            f"RUNTIME_BASELINE_FILES must include {tg}; "
            f"current list: {RUNTIME_BASELINE_FILES}"
        )


# ---------------------------------------------------------------------------
# test_worktree_normalization_audit_is_read_only
# ---------------------------------------------------------------------------

def test_worktree_normalization_audit_is_read_only(monkeypatch):
    """worktree_normalization_audit must only call git status; it must never
    issue destructive git commands (add, reset, checkout, push, commit, restore,
    clean, rm).  The result must correctly categorize files into the four groups:
    source, generated_artifacts, deletions, untracked."""
    import trading_bot.clean_bot.ops_gates as _ops
    from trading_bot.clean_bot.ops_gates import worktree_normalization_audit

    # Representative git --porcelain=v1 output (2-char XY prefix + space + path)
    fake_porcelain = (
        " M trading_bot/clean_bot/paper_live.py\n"      # tracked source modification
        " M data/clean_paper_state.json\n"               # tracked artifact modification
        " D docs/patch_reports/OLD_MANIFEST.txt\n"       # tracked deletion
        "?? data/new_report.json\n"                      # untracked file
        "?? docs/TR_OPS_01_REPORT.md\n"                  # untracked file
    )

    captured_commands: list[list[str]] = []

    def mock_run(cmd, **kwargs):
        captured_commands.append(list(cmd))
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = fake_porcelain
        fake.stderr = ""
        return fake

    monkeypatch.setattr(_ops.subprocess, "run", mock_run)

    result = worktree_normalization_audit()

    # --- Read-only verification: only git status commands allowed ---
    assert len(captured_commands) >= 1, "Expected at least one subprocess command"
    destructive_tokens = frozenset({
        "add", "reset", "checkout", "push", "commit",
        "restore", "clean", "rm", "remove", "delete", "stage",
    })
    for cmd in captured_commands:
        cmd_words = " ".join(cmd).lower().split()
        for token in destructive_tokens:
            assert token not in cmd_words, (
                f"Forbidden git operation '{token}' found in command: {' '.join(cmd)}"
            )
        assert any("git" in tok.lower() for tok in cmd), (
            f"Expected only git commands, got: {' '.join(cmd)}"
        )

    # --- Structure verification ---
    for key in ("source", "generated_artifacts", "deletions", "untracked", "counts"):
        assert key in result, f"Missing key '{key}' in audit result"
    assert result.get("read_only") is True

    # --- Categorization verification ---
    assert any("paper_live.py" in f for f in result["source"]), (
        f"paper_live.py (tracked .py modification) should be in source; "
        f"got source={result['source']}"
    )
    assert any("clean_paper_state.json" in f for f in result["generated_artifacts"]), (
        f"clean_paper_state.json (tracked .json modification) should be in "
        f"generated_artifacts; got artifacts={result['generated_artifacts']}"
    )
    assert any("OLD_MANIFEST" in f for f in result["deletions"]), (
        f"OLD_MANIFEST.txt (tracked deletion) should be in deletions; "
        f"got deletions={result['deletions']}"
    )
    assert len(result["untracked"]) >= 1, (
        f"Expected at least one untracked file; got untracked={result['untracked']}"
    )
    assert result["counts"]["source"] == len(result["source"])
    assert result["counts"]["generated_artifacts"] == len(result["generated_artifacts"])
    assert result["counts"]["deletions"] == len(result["deletions"])
    assert result["counts"]["untracked"] == len(result["untracked"])


# ---------------------------------------------------------------------------
# test_gate_blocked_by_preexisting_config_modification (integration)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modified_file", [
    "trading_bot/config.py",
    "trading_bot/core/client.py",
    "trading_bot/core/telegram_control.py",
    "trading_bot/core/lsr_v2_telegram_notification_bridge.py",
    "trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py",
    "trading_bot/core/lsr_v2_telegram_trade_dashboard.py",
    "trading_bot/core/notifier.py",
    "trading_bot/core/telegram_proactive.py",
])
def test_gate_blocked_by_preexisting_modification(tmp_path, modified_file):
    """Integration: check_no_live_modified in run_phase_1_2_recertification must
    return status='BLOCKED' when config.py, core/client.py, or any Telegram module
    (including all three lsr_v2 bridge modules) has been modified before the gate
    runs — not just during the run.

    This test exercises the gate wrapper in the pipeline module
    (run_phase_1_2_recertification.check_no_live_modified), not the underlying
    ops_gates.no_live_modified function in isolation.
    """
    from trading_bot.clean_bot.ops_gates import generate_approved_baseline
    from trading_bot.run_phase_1_2_recertification import check_no_live_modified

    # All Telegram bridge modules that the gate must cover
    monitored = [
        "trading_bot/config.py",
        "trading_bot/core/client.py",
        "trading_bot/core/telegram_control.py",
        "trading_bot/core/lsr_v2_telegram_notification_bridge.py",
        "trading_bot/core/lsr_v2_telegram_position_monitor_bridge.py",
        "trading_bot/core/lsr_v2_telegram_trade_dashboard.py",
        "trading_bot/core/notifier.py",
        "trading_bot/core/telegram_proactive.py",
    ]

    # Create fake approved versions in a temp project tree
    for rel in monitored:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# approved: {rel}", encoding="utf-8")

    # Snapshot approved hashes into the baseline file
    baseline_path = tmp_path / "ops_approved_baseline.json"
    generate_approved_baseline(baseline_path, files=monitored, project_root=tmp_path)

    # Pre-existing modification: the file is changed BEFORE the gate runs
    (tmp_path / modified_file).write_text("# tampered content", encoding="utf-8")

    # Call through the pipeline gate wrapper — not ops_gates directly
    result = check_no_live_modified(
        baseline_path=baseline_path,
        project_root=tmp_path,
        files=monitored,
    )

    assert result["status"] == "BLOCKED", (
        f"Gate must be BLOCKED when {modified_file} is pre-modified; "
        f"got status={result['status']!r}, issues={result['issues']}"
    )
    assert result["files_checked"] == len(monitored)
    assert any(modified_file in iss for iss in result["issues"]), (
        f"Expected an issue mentioning '{modified_file}'; got issues={result['issues']}"
    )
    modified_result = result["file_results"].get(modified_file, {})
    assert modified_result.get("status") == "MODIFIED", (
        f"Expected file_results[{modified_file!r}].status == 'MODIFIED'; "
        f"got {modified_result.get('status')!r}"
    )
