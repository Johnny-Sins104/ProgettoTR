# Prompt 29.4.4s-10aq — LSR-v2 third open paper-position monitor

## Scope
Adds a read-only monitor for the third supervised LSR-v2 paper trade opened by `29.4.4s-10ao` and verified by `29.4.4s-10ap`.

## Outputs
- `data/lsr_v2_third_open_position_monitor_report.json`
- `data/lsr_v2_third_open_position_monitor.jsonl`

## Checks
- third submit execution report is PASS
- third position lifecycle report is PASS
- exactly one open third LSR-v2 paper position exists
- paper state and paper status are aligned
- no pending order / fourth re-entry is detected
- current price, unrealized PnL, R multiple and SL/TP hit diagnostics are computed

## Safety
No submit, no close, no broker call, no `paper_state.json` mutation, no `paper_status.json` mutation, no live/testnet/exchange broker path.

## Next step
Use `run_lsr_v2_telegram_position_monitor_bridge.py` to send the SL/TP bar for the third open paper position. If `close_required_diagnostic=true`, proceed to the third trade close preflight.
