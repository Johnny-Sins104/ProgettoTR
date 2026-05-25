# PROMPT 29.4.4r-2 PATCH REPORT — Legacy paper position quarantine / clean-state preflight

## Scope

This patch adds a state sanitation layer after the 29.4.4r-OBS discovery that legacy `ScoreOnly+Meta_OK` paper orders opened positions outside the guarded bridge/candidate/handoff path.

## Files added / changed

- `trading_bot/core/paper_legacy_position_quarantine.py`
- `trading_bot/run_paper_legacy_position_quarantine.py`
- `trading_bot/test_paper_legacy_position_quarantine.py`
- `trading_bot/config.py`
- `docs/patch_reports/PROMPT_29_4_4R2_PATCH_REPORT.md`
- `trading_bot/docs/patch_reports/PROMPT_29_4_4R2_PATCH_REPORT.md`

## Behavior

The runner supports three operator-controlled modes:

```cmd
python trading_bot\run_paper_legacy_position_quarantine.py --report-only
python trading_bot\run_paper_legacy_position_quarantine.py --quarantine
python trading_bot\run_paper_legacy_position_quarantine.py --reset-paper-state --confirm-reset
```

`--report-only` detects legacy orders/positions in active paper state and writes `data/paper_legacy_position_quarantine_report.json`.

`--quarantine` creates a backup and marks legacy orders/positions with metadata fields such as `legacy_contaminated=true`, `legacy_quarantined=true`, and `excluded_from_guarded_diagnostics=true`. It does not close or delete positions.

`--reset-paper-state --confirm-reset` creates a backup, resets active `paper_state.json`, `paper_status.json`, and `paper_position_monitor.json` to a clean paper state, and rotates active `paper_events.jsonl` to a fresh log containing `PAPER_LEGACY_STATE_RESET`. Historical contaminated files are preserved under `data/paper_legacy_quarantine_backups/<timestamp>/`.

## Safety

No live, no testnet, no exchange broker, no broker submit, no order submit, no position open. This patch only audits/quarantines/resets local paper state files after explicit operator commands.

## Validation

Sandbox validation passed:

```cmd
python trading_bot\test_paper_legacy_position_quarantine.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```

## Post-install procedure

1. Run report-only.
2. Optionally run quarantine to mark contaminated objects.
3. Run reset only with explicit `--confirm-reset`.
4. Verify `open_positions=0` and leakage guard report is clean on fresh active logs.
5. Only then resume 4h/8h observation.
