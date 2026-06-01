from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.liquidity_sweep_reversal_v2 import LSRV2Settings, run_lsr_v2_candidate_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-6b LSR-v2 timeframe strictness + quality report")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--input-path", default=None)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--allow-timeframe-fallback", action="store_true", help="Allow loading a market-data file whose detected timeframe differs from --timeframe; default is strict reject.")
    parser.add_argument("--no-strict-timeframe", action="store_true", help="Disable strict timeframe reporting. Not recommended for validation runs.")
    parser.add_argument("--pool-lookback", type=int, default=20)
    parser.add_argument("--confirmation-window", type=int, default=4)
    parser.add_argument("--retest-window", type=int, default=6)
    parser.add_argument("--min-sweep-bps", type=float, default=2.0)
    parser.add_argument("--retest-tolerance-bps", type=float, default=8.0)
    parser.add_argument("--stop-buffer-bps", type=float, default=2.0)
    parser.add_argument("--target-rr", type=float, default=2.0)
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument("--fee-rate", type=float, default=0.0004)
    parser.add_argument("--spread-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--max-cost-to-r", type=float, default=0.35)
    parser.add_argument("--require-volume-confirmation", action="store_true")
    parser.add_argument("--allow-ready-without-retest", action="store_true")
    args = parser.parse_args()

    settings = LSRV2Settings(
        data_dir=args.data_dir,
        input_path=args.input_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
        strict_timeframe=not bool(args.no_strict_timeframe),
        allow_timeframe_fallback=bool(args.allow_timeframe_fallback),
        pool_lookback=args.pool_lookback,
        confirmation_window=args.confirmation_window,
        retest_window=args.retest_window,
        min_sweep_bps=args.min_sweep_bps,
        retest_tolerance_bps=args.retest_tolerance_bps,
        stop_buffer_bps=args.stop_buffer_bps,
        target_rr=args.target_rr,
        min_rr=args.min_rr,
        fee_rate=args.fee_rate,
        spread_bps=args.spread_bps,
        slippage_bps=args.slippage_bps,
        max_cost_to_r=args.max_cost_to_r,
        require_volume_confirmation=bool(args.require_volume_confirmation),
        require_retest_for_candidate_ready=not bool(args.allow_ready_without_retest),
    )
    report = run_lsr_v2_candidate_audit(settings)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "input_rows": report.get("input_rows"),
        "input_path": report.get("input_path"),
        "requested_timeframe": report.get("requested_timeframe"),
        "detected_timeframe": report.get("detected_timeframe"),
        "timeframe_match": report.get("timeframe_match"),
        "strict_timeframe": report.get("strict_timeframe"),
        "allow_timeframe_fallback": report.get("allow_timeframe_fallback"),
        "candidates_count": report.get("candidates_count"),
        "candidate_ready_count": report.get("candidate_ready_count"),
        "retest_ready_count": report.get("retest_ready_count"),
        "candidate_density_pct": (report.get("summary") or {}).get("candidate_density_pct") if isinstance(report.get("summary"), dict) else None,
        "ready_density_pct": (report.get("summary") or {}).get("ready_density_pct") if isinstance(report.get("summary"), dict) else None,
        "quality_A": (report.get("summary") or {}).get("quality_A") if isinstance(report.get("summary"), dict) else None,
        "quality_B": (report.get("summary") or {}).get("quality_B") if isinstance(report.get("summary"), dict) else None,
        "quality_C": (report.get("summary") or {}).get("quality_C") if isinstance(report.get("summary"), dict) else None,
        "orders_submitted_by_lsr_v2": report.get("orders_submitted_by_lsr_v2", 0),
        "positions_opened_by_lsr_v2": report.get("positions_opened_by_lsr_v2", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "jsonl": report.get("jsonl"),
        "report": report.get("report"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
