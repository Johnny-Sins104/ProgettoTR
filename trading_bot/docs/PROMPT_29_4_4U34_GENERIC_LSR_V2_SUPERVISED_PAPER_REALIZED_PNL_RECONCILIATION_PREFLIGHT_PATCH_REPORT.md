# Prompt 29.4.4u-34 — Generic LSR-v2 supervised paper realized PnL reconciliation preflight

## Scope

This patch adds a read-only, fail-closed preflight for future realized PnL reconciliation after a supervised paper close execution.

## Added files

- `trading_bot/core/lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight.py`
- `trading_bot/run_lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight.py`
- `trading_bot/tests/test_lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight.py`
- `trading_bot/docs/PROMPT_29_4_4U34_GENERIC_LSR_V2_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_PATCH_REPORT.md`
- `docs/patch_reports/PATCH_29_4_4U34_MANIFEST.txt`

## Safety contract

The patch consumes the u-33 close execution report and models the future realized-PnL reconciliation requirements. It does not reconcile PnL, does not perform final audit/postmortem, does not call brokers, does not mutate `paper_state` or `paper_status`, does not submit/close orders, does not start schedulers, does not send Telegram/network messages, and does not enable live/testnet/exchange access.

Expected validation state remains blocked because there is no real close execution, no broker close receipt, no closed paper position, no runtime values, and no operator gates.

## Expected decision

`LSR_V2_GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_READY`

## Next patch

`29.4.4u-35 — Generic LSR-v2 supervised paper final audit preflight`
