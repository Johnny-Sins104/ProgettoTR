# Prompt 30.3.0D - First supervised LSR-v2 paper submit execution

## Scope

This step executed the first supervised LSR-v2 paper-only submit from the
validated preflight chain.

It used the existing execution boundary and both required operator confirmations.
No live, testnet, or exchange broker path was enabled.

## Pre-execution state

- `paper_state.json`: 0 orders, 0 positions.
- `paper_status.json`: `open_positions=0`, `pending_orders=0`.
- Submit preflight: `LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_READY`.
- Cycle: `pc_000517_99a0e0a7`.

## Execution controls

```text
LSR_V2_PAPER_SUBMIT_ARM=1
LSR_V2_PAPER_SUBMIT_CONFIRMATION=I_UNDERSTAND_SINGLE_PAPER_ORDER
LSR_V2_PAPER_SUBMIT_EXECUTE=1
LSR_V2_PAPER_SUBMIT_EXECUTE_CONFIRMATION=I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY
LSR_V2_PAPER_SUBMIT_MAX_ORDERS=1
```

## Execution result

- Decision: `LSR_V2_SINGLE_PAPER_ORDER_EXECUTED`
- Status: `PASS`
- Symbol: `BTC/USDT`
- Side: `SELL`
- Order id: `po_a8407626023b47cf`
- Position id: `pp_e8777c510d2f4031`
- Entry: `99076.7`
- Stop loss: `99367.46952`
- Take profit: `98495.16096`
- Quantity: `0.008597875`
- Total notional: `851.8490865205`
- Total risk amount: `2.5`

Safety state:

- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- `orders_submitted_by_lsr_v2_execution=1`
- `positions_opened_by_lsr_v2_execution=1`

## Status reconciliation

After execution, `paper_state.json` correctly had one open position while
`paper_status.json` was stale. The reconciliation was first run in audit mode,
then applied with explicit sync confirmation:

```text
LSR_V2_PAPER_STATUS_SYNC_ENABLE=1
LSR_V2_PAPER_STATUS_SYNC_CONFIRMATION=I_UNDERSTAND_SYNC_PAPER_STATUS_ONLY
```

Result:

- Decision: `LSR_V2_PAPER_STATUS_SYNC_APPLIED`
- `paper_status_modified=true`
- `open_positions=1`
- `pending_orders=0`
- backup: `data\paper_status_reconciliation_backups\paper_status_20260601T110023Z.json`

## Open-position monitor

Monitor result:

- Decision: `LSR_V2_OPEN_POSITION_MONITOR_READY`
- Open LSR-v2 positions: `1`
- Paper state consistency: `true`
- Paper status consistency: `true`
- Current price: `99197.0`
- Unrealized PnL: `-1.0343243625`
- Current R multiple: `-0.413729745`
- Close required diagnostic: `false`

## Validation

- `tools\run_checks.py --require-deps`: PASS, 30 smoke tests passed.

## Operational conclusion

The bot has now performed one supervised paper-only LSR-v2 order through the
local paper broker. The position is open and being tracked. The next operational
step is close monitoring and, when SL/TP or a manual supervised close condition
is met, running the supervised paper close preflight/execution chain.
