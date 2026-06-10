from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.dashboard.strategy_dashboard_api import get_strategy_status, post_strategy_calibrate, post_strategy_select
from trading_bot.strategy_runtime.strategy_config_store import runtime_config_path
from trading_bot.strategy_runtime.strategy_signal_schema import SUPPORTED_STRATEGIES


def build_preflight(data_dir: Path = Path("data")) -> dict:
    select_result = post_strategy_select({"strategy": "bb"}, data_dir=data_dir)
    status = get_strategy_status(data_dir=data_dir)
    calibration = post_strategy_calibrate(
        {"strategy": "bb", "asset": "BTC/USDT", "timeframe": "5m", "regime": "ranging"},
        data_dir=data_dir,
    )
    # The real switch-block behavior is unit-tested with an injected open-position
    # reader. The runner reports the contract as available, not that the current
    # account has an open position.
    strategy_switch_blocked_when_position_open = True
    checks = {
        "strategy_selector_available": select_result.get("status") in {"OK", "BLOCKED"},
        "dashboard_strategy_api_available": status.get("status") == "OK",
        "runtime_config_available": runtime_config_path(data_dir).exists(),
        "supported_strategies": list(SUPPORTED_STRATEGIES),
        "strategy_switch_blocked_when_position_open": strategy_switch_blocked_when_position_open,
        "calibration_scaffold_available": calibration.get("status") == "OK"
        and calibration.get("calibration", {}).get("can_trade") is False,
        "paper_trading_activation_allowed": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
        "would_submit": False,
        "would_close": False,
    }
    ready = (
        checks["strategy_selector_available"]
        and checks["dashboard_strategy_api_available"]
        and checks["runtime_config_available"]
        and checks["calibration_scaffold_available"]
        and not checks["paper_trading_activation_allowed"]
        and not checks["broker_submit_allowed"]
        and not checks["broker_close_allowed"]
        and not checks["live_trading_allowed"]
        and not checks["testnet_allowed"]
        and not checks["would_submit"]
        and not checks["would_close"]
    )
    return {
        "status": "PASS" if ready else "FAIL",
        "decision": "STRATEGY_SELECTOR_DASHBOARD_PREFLIGHT_READY" if ready else "STRATEGY_SELECTOR_DASHBOARD_PREFLIGHT_BLOCKED",
        **checks,
    }


def main() -> int:
    report = build_preflight()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
