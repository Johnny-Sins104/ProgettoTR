from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.strategy_runtime.strategy_shadow_report import build_and_write_shadow_report


def build_runner_report(
    *,
    data_dir: Path = Path("data"),
    asset: str = "XRP/USDT",
    timeframe: str = "5m",
    max_rows: int = 500,
) -> dict:
    report = build_and_write_shadow_report(data_dir=data_dir, asset=asset, timeframe=timeframe, max_rows=max_rows)
    keys = [
        "status",
        "decision",
        "active_strategy",
        "active_strategy_label",
        "shadow_signal_available",
        "shadow_only",
        "single_strategy_execution_confirmed",
        "auto_strategy_execution_allowed",
        "paper_trading_activation_allowed",
        "broker_submit_allowed",
        "broker_close_allowed",
        "live_trading_allowed",
        "testnet_allowed",
        "would_submit",
        "would_close",
    ]
    return {key: report[key] for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run selected-strategy shadow signal execution preflight.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--asset", default="XRP/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--max-rows", type=int, default=500)
    args = parser.parse_args()
    report = build_runner_report(
        data_dir=Path(args.data_dir),
        asset=args.asset,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
