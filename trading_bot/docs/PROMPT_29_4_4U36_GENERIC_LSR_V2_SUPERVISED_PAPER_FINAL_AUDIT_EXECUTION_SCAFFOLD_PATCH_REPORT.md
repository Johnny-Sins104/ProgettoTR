# Prompt 29.4.4u-36 — Generic LSR-v2 supervised paper final audit execution scaffold

## Intent

This patch adds a guarded scaffold for the future supervised paper-only final audit execution stage. It consumes the `29.4.4u-35` final-audit preflight report and models the execution contract without running a final audit, postmortem, broker operation, scheduler, Telegram send, or paper state/status mutation.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py`
- `trading_bot/docs/PROMPT_29_4_4U36_GENERIC_LSR_V2_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_SCAFFOLD_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U36_MANIFEST.txt`

## Expected validation decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_SCAFFOLD_READY`

## Readiness flags

Expected ready/model flags in the normal local validation path:

- `generic_supervised_paper_final_audit_execution_scaffold_ready=true`
- `generic_final_audit_execution_scaffold_ready=true`
- `paper_final_audit_execution_scaffold_ready=true`
- `generic_final_audit_execution_scaffold_model_ready=true`
- `generic_final_audit_execution_scaffold_patch_ready=true`
- `final_audit_execution_scaffold_diagnostic_available=true`
- `final_audit_execution_scaffold_contract_shape_modelable=true`

## Safety posture

This patch remains scaffold-only and fail-closed. Expected blocked fields:

- `generic_final_audit_execution_allowed=false`
- `paper_final_audit_ready=false`
- `would_run_final_audit=false`
- `would_run_postmortem=false`
- `would_reconcile_realized_pnl=false`
- `would_submit=false`
- `would_close=false`
- `would_call_paper_broker_submit=false`
- `would_call_paper_broker_close=false`
- `paper_state_modified_by_generic_final_audit_execution_scaffold=false`
- `paper_status_modified_by_generic_final_audit_execution_scaffold=false`
- `orders_submitted_by_generic_final_audit_execution_scaffold=0`
- `positions_opened_by_generic_final_audit_execution_scaffold=0`
- `positions_closed_by_generic_final_audit_execution_scaffold=0`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`

## Required future controls before real final audit execution

The scaffold requires all of the following before a later explicit execution patch can do any real final audit work:

- Broker submit receipt.
- Broker close receipt.
- Real close execution.
- Closed paper position.
- Realized-PnL reconciliation ready.
- Realized-PnL write available.
- Re-arm, submit, close, realized-PnL, and final-audit operator gates.
- Runtime values present and validated.
- `paper_only=true` and `max_open_positions=1`.
- Live/testnet/exchange disabled.
- A later explicit final-audit execution patch.

## Validation command

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main
$env:PYTHONPATH="$PWD;$PWD\trading_bot"

$Log="$env:USERPROFILE\Desktop\VALIDATION_29_4_4u36.txt"

"=== compileall ===" | Out-File $Log
python -m compileall -q trading_bot 2>&1 | Tee-Object -FilePath $Log -Append

"=== pytest ===" | Tee-Object -FilePath $Log -Append
python -m pytest -q trading_bot\tests\test_lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py 2>&1 | Tee-Object -FilePath $Log -Append

"=== runner ===" | Tee-Object -FilePath $Log -Append
python trading_bot\run_lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py 2>&1 | Tee-Object -FilePath $Log -Append

Write-Host "Log creato:" $Log -ForegroundColor Green
```

## Next patch

`29.4.4u-37 — Generic LSR-v2 supervised paper final audit execution`
