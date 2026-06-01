# Prompt 30.3.0C - Bounded replay and submit preflight readiness

## Scope

This patch turns replay paper mode into a bounded operational drill.

New runner controls:

- `--max-cycles N`: stop after N completed cycles.
- `--market-data-replay-start-offset N`: start replay from a chosen candle offset.
- `--cycle-artifacts` / `--no-cycle-artifacts`: choose whether to run heavy artifact/report generation after each cycle.

Continuous paper/replay drills now have a lightweight path that does not hang
after `CYCLE_COMPLETED` on expensive artifact generation. Full artifacts remain
available explicitly and remain the default for `--once` smoke runs.

## Bounded replay result

Command shape:

```powershell
python trading_bot\run_paper_trading.py --mode paper --symbols BTC/USDT --timeframe 5m --balance 1000 --poll-seconds 0 --max-cycles 3 --market-data-mode replay --market-data-cache-dir data --market-data-replay-start-offset 500 --market-data-replay-step 25 --no-cycle-artifacts --no-telegram-proactive
```

Result:

- cycle 513: `scanned=1`, `errors=0`, replay offset `500`, candidate not ready.
- cycle 514: `scanned=1`, `errors=0`, replay offset `525`, candidate ready.
- cycle 515: `scanned=1`, `errors=0`, replay offset `550`, candidate ready.
- `MAX_CYCLES_REACHED` emitted with `completed_cycles=3`.
- Process exited cleanly.

## Supervised diagnostic readiness

With explicit operator bridge confirmation:

```powershell
--lsr-v2-bridge-operator-enable --lsr-v2-bridge-confirm I_UNDERSTAND_LSR_V2_PAPER_SUPERVISED_ONLY
```

Latest validated cycle:

```text
pc_000517_99a0e0a7
```

Readiness chain:

- Operator route audit: `LSR_V2_OPERATOR_ROUTE_AUDIT_READY_DIAGNOSTIC`
- Order intent audit: `LSR_V2_ORDER_INTENT_AUDIT_READY_DIAGNOSTIC`
- Paper broker handoff dry-run: `LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC`
- Supervised paper submit preflight: `LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_READY`

Key counts:

- `would_route_count=1`
- `would_create_order_count=1`
- `payload_valid_count=1`
- `would_prepare_submit_count=1`
- `total_notional=851.8490865205`
- `total_risk_amount=2.5`

## Safety state

The chain is ready as a supervised diagnostic preflight only. It remains
fail-closed:

- `submit_enabled=false`
- `broker_submit_called=false`
- `paper_order_submission_enabled=false`
- `routing_enabled=false`
- `execution_enabled=false`
- `live_enabled=false`
- `testnet_enabled=false`
- `exchange_broker_enabled=false`
- orders submitted: `0`
- positions opened: `0`

## Validation

- `tools\run_checks.py --require-deps`: PASS, 30 smoke tests passed.
- `python -m pytest`: PASS, 1010 passed, 2 warnings.

## Operational conclusion

Paper replay can now run bounded cycles, find LSR-v2 runtime candidates, and
advance through the supervised submit preflight chain without actually
submitting orders. The next step is the already-scaffolded supervised submit
execution path, still behind operator confirmation and fail-closed controls.
