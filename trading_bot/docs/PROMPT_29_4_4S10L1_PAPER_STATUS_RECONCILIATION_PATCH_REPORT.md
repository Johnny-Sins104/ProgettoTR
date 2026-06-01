# Prompt 29.4.4s-10l-1 — LSR-v2 paper status reconciliation / open-position status sync audit

## Scope
Adds an audit-first reconciliation layer between `paper_state.json` and `paper_status.json` after the first supervised LSR-v2 paper-only order.

The active broker state remains the source of truth. `paper_status.json` is treated as a derived summary and is only modified when an explicit operator sync confirmation is supplied.

## Added files

- `trading_bot/core/lsr_v2_paper_status_reconciliation.py`
- `trading_bot/run_lsr_v2_paper_status_reconciliation.py`
- `trading_bot/tests/test_lsr_v2_paper_status_reconciliation.py`

## Outputs

- `data/lsr_v2_paper_status_reconciliation_report.json`
- `data/lsr_v2_paper_status_reconciliation.jsonl`
- `data/paper_status_reconciliation_backups/paper_status_<timestamp>.json` when sync is applied

## Default behavior

Default is audit-only:

- `sync_enabled=false`
- `paper_status_modified=false`
- no order submission
- no position opening
- no broker submit
- no automatic close
- no automatic re-entry

## Optional sync controls

```powershell
$env:LSR_V2_PAPER_STATUS_SYNC_ENABLE="1"
$env:LSR_V2_PAPER_STATUS_SYNC_CONFIRMATION="I_UNDERSTAND_SYNC_PAPER_STATUS_ONLY"
```

When enabled and confirmed, the patch backs up `paper_status.json`, then rewrites only summary fields derived from `paper_state.json`:

- `open_positions`
- `pending_orders`
- `positions`
- `position_monitor.open_position_count`
- `position_monitor.positions`
- `position_monitor.account.*`
- reconciliation metadata

## Safety invariants

- no new order
- no new position
- no broker submit
- no automatic close
- no automatic re-entry
- no live
- no testnet
- no exchange broker
- no mutation of `paper_state.json`
