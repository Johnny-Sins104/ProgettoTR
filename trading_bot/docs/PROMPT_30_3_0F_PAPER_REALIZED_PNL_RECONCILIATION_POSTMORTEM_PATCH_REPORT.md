# Patch 30.3.0F - Paper Realized PnL Reconciliation And Postmortem

## Objective

Create a read-only bundle that reconciles the realized PnL, fees, balance/equity delta, and postmortem for the first supervised LSR-v2 paper trade.

Prerequisite 30.3.0E was present and did not produce `FAIL`.

## Result

- PnL status: `WARN`
- PnL decision: `LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_WARN_NON_BLOCKING`
- Postmortem status: `WARN`
- Postmortem decision: `LSR_V2_PAPER_TRADE_POSTMORTEM_WARN_NON_BLOCKING`
- Recommendation: `prepare_second_order_gate_default_off`

The warning is non-blocking. The accounting reconciles when position-level realized PnL is treated as gross price PnL minus exit fee only, with entry fee accounted separately in the balance delta.

## PnL Reconciliation

- Side: `SELL`
- Entry price: `99076.7`
- Exit price: `99367.46952`
- Quantity: `0.008597875`
- Gross PnL: `-2.4999999868`
- Recorded position realized PnL: `-2.8417396196`
- Entry fee: `1.703698164`
- Exit fee: `0.3417396328`
- Total fees: `2.0454377968`
- Fee accounting mode: `net_includes_exit_fee_only`
- PnL fee inclusion scope: `exit_fee_only`
- Account net PnL expected: `-4.5454377836`
- Balance delta: `-4.5454377836`

## Postmortem

- Trade direction: `SELL`
- Close reason: `SL`
- SL distance: `290.76952`
- TP distance: `581.53904`
- Slippage: `0.0`
- Signal quality: `unknown`
- Should block next-order experimentation: `false`

## Files Added

- `trading_bot/core/lsr_v2_paper_realized_pnl_reconciliation.py`
- `trading_bot/run_lsr_v2_paper_realized_pnl_reconciliation.py`
- `trading_bot/tests/test_lsr_v2_paper_realized_pnl_reconciliation.py`
- `docs/patch_reports/PATCH_30_3_0F_MANIFEST.txt`
- `trading_bot/docs/PROMPT_30_3_0F_PAPER_REALIZED_PNL_RECONCILIATION_POSTMORTEM_PATCH_REPORT.md`

## Runtime Artifacts

- `data/lsr_v2_paper_realized_pnl_reconciliation_report.json`
- `data/lsr_v2_paper_realized_pnl_reconciliation.jsonl`
- `data/lsr_v2_paper_trade_postmortem_report.json`
- `data/lsr_v2_paper_trade_postmortem.jsonl`

## Safety Confirmation

- No live mode enabled.
- No testnet mode enabled.
- No exchange broker enabled.
- No broker submit by reconciliation/postmortem.
- No broker close by reconciliation/postmortem.
- No order submitted.
- No position opened.
- No position closed.
- No scheduler started.
- `paper_state.json` not modified.
- `paper_status.json` not modified.

## Stop-Gate

Patch 30.3.0F does not produce `FAIL`.

The next allowed patch is 30.3.0G: second supervised paper order execution gate, default-off and diagnostic only.

## Validation

- `python -m compileall -q trading_bot/core/lsr_v2_paper_realized_pnl_reconciliation.py trading_bot/run_lsr_v2_paper_realized_pnl_reconciliation.py`: PASS
- `pytest trading_bot/tests/test_lsr_v2_paper_realized_pnl_reconciliation.py -q`: PASS, `7 passed`
- Final E-H validation: PASS, targeted E/F/G/H tests `29 passed`; smoke `30 passed`; full `pytest trading_bot/tests -q` `867 passed`
