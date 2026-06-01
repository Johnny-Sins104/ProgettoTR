# PROMPT 29.4.4u-15 — Generic LSR-v2 runtime snapshot engine-runner adapter visibility parity lock

## Scope

Lock-only/read-only/fail-closed patch that freezes the adapter visibility parity audited by 29.4.4u-14.

## Added files

- `trading_bot/core/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.py`
- `trading_bot/run_lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.py`
- `trading_bot/tests/test_lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.py`
- `trading_bot/docs/PROMPT_29_4_4U15_GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U15_MANIFEST.txt`

## Expected decision

`LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_READY`

## Safety

No submit, no open, no close, no broker call, no scheduler, no Telegram network send, no paper state/status mutation, no live/testnet/exchange broker, no ordinal expansion.
