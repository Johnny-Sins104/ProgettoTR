# Prompt 29.4.4s-10 — LSR-v2 paper-supervised bridge scaffold / fail-closed runtime audit

## Scope

Adds a diagnostic-only LSR-v2 paper-supervised bridge scaffold after the validated promotion gate.

Approved research profile:

- `LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24`
- `retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24`
- selected overlay: `combo_loss3_dd10_side_cap`

## Files

- `trading_bot/core/lsr_v2_paper_supervised_bridge.py`
- `trading_bot/run_lsr_v2_paper_supervised_bridge.py`
- `trading_bot/tests/test_lsr_v2_paper_supervised_bridge.py`
- `trading_bot/docs/PROMPT_29_4_4S10_LSR_V2_PAPER_SUPERVISED_BRIDGE_PATCH_REPORT.md`

## Artifacts

- `data/lsr_v2_paper_supervised_bridge_report.json`
- `data/lsr_v2_paper_supervised_bridge_audit.jsonl`

## Safety invariants

- no live
- no testnet
- no exchange broker
- no broker call
- no paper order submission
- no position opening
- no paper state mutation
- no runtime routing
- no automatic activation
- `would_submit=false` always
- `promotion_ready=false` always

## Decisions

- `LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_NO_CANDIDATES`
- `KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_GATE_MISSING`
- `KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_FAIL_CLOSED`
- `KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_ERROR`
