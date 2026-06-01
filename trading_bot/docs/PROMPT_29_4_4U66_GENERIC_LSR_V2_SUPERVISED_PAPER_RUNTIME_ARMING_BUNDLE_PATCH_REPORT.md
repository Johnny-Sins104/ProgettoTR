# Prompt 29.4.4u-66 — Generic LSR-v2 supervised paper runtime arming bundle

## Scope

This macro-patch adds the generic LSR-v2 supervised paper runtime arming bundle.
It groups three homogeneous gate steps into one patch:

1. runtime arming preflight
2. runtime arming execution scaffold
3. runtime arming execution

The bundle consumes the validated `29.4.4u-65` runtime activation terminal audit
bundle report and emits four artifacts under `data/`:

- `lsr_v2_generic_supervised_paper_runtime_arming_preflight_report.json`
- `lsr_v2_generic_supervised_paper_runtime_arming_execution_scaffold_report.json`
- `lsr_v2_generic_supervised_paper_runtime_arming_execution_report.json`
- `lsr_v2_generic_supervised_paper_runtime_arming_bundle_report.json`

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_arming_bundle.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_arming_preflight.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_arming_execution_scaffold.py`
- `trading_bot/core/lsr_v2_generic_supervised_paper_runtime_arming_execution.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_runtime_arming_bundle.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_runtime_arming_bundle.py`
- `trading_bot/docs/PROMPT_29_4_4U66_GENERIC_LSR_V2_SUPERVISED_PAPER_RUNTIME_ARMING_BUNDLE_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U66_MANIFEST.txt`

## Safety contract

The patch is read-only-by-default and fail-closed. It does not:

- arm the paper runtime
- submit orders
- close positions
- call a broker
- start a scheduler
- send Telegram or network messages
- mutate `paper_state`
- mutate `paper_status`
- enable live, testnet, or exchange access
- expand ordinal trade permissions

The execution substep removes only the explicit future runtime arming execution
patch blocker because this macro-patch includes that execution model. Runtime
arming remains blocked until complete runtime lifecycle evidence, broker receipts,
runtime values, paper-only constraints, and operator gates exist.

## Expected validation state

Expected bundle decision:

```text
LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ARMING_BUNDLE_READY
```

Expected blocked flags:

```text
generic_paper_runtime_arming_allowed=false
generic_paper_runtime_arming_execution_allowed=false
generic_runtime_activation_terminal_audit_execution_allowed=false
generic_runtime_activation_envelope_execution_allowed=false
generic_integrated_operation_execution_allowed=false
future_integrated_operation_allowed=false
paper_runtime_arming_runtime_executed=false
would_arm_paper_runtime=false
would_submit=false
would_close=false
would_send_telegram=false
would_start_scheduler=false
```

## Sandbox validation

```text
compileall: PASS
pytest u66 bundle: 6 passed
pytest available generic LSR-v2: 165 passed
runner bundle: PASS
```

## Next patch

```text
29.4.4u-67 — Generic LSR-v2 supervised paper integrated dry-run runtime bundle
```
