"""Paper-first launcher for Prompt 29.

The historical live loop in ``main.py`` remains available for research, but this
entrypoint refuses real-money execution.  It routes to the paper engine by
default and requires future explicit hardening before any live mode is allowed.

Prompt 29.4.4t-4 adds a read-only LSR-v2 dashboard/lifecycle banner before the
paper runner starts.  The banner reads already validated artifacts only; it does
not submit/close orders, mutate paper_state/paper_status, start schedulers, or
send Telegram messages.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:  # read-only launcher banner; fail closed if unavailable
    from core.lsr_v2_launcher_read_only_dashboard_banner import emit_lsr_v2_launcher_read_only_dashboard_banner
except Exception:  # pragma: no cover - launcher must remain usable if artifact module is absent
    emit_lsr_v2_launcher_read_only_dashboard_banner = None  # type: ignore[assignment]


BLOCKED_MODES = {"live", "testnet", "live-supervised", "live-auto"}
READ_ONLY_TOOL_FLAGS = {
    "--paper-tools",
    "--paper-status",
    "--paper-performance",
    "--paper-blockers",
    "--paper-opportunities",
    "--paper-shadow-thresholds",
    "--paper-support-rejection",
    "--clean-backtest",
    "--clean-optimize",
    "--clean-cleanup-plan",
    "--clean-frequency-audit",
    "--clean-scalping-1m-audit",
    "--clean-monitor",
}


def _arg_value(argv: list[str], name: str) -> str:
    prefix = f"{name}="
    for idx, arg in enumerate(argv):
        if arg.startswith(prefix):
            return arg.split("=", 1)[1]
        if arg == name and idx + 1 < len(argv):
            return argv[idx + 1]
    return ""


def _live_requested(argv: list[str]) -> bool:
    mode = _arg_value(argv, "--mode").strip().lower()
    return any(arg == "--live" for arg in argv) or mode in BLOCKED_MODES


def _ensure_arg(argv: list[str], name: str, value: str) -> None:
    if any(arg == name or arg.startswith(f"{name}=") for arg in argv):
        return
    argv.extend([name, value])


def _replace_mode(argv: list[str], value: str) -> None:
    for idx, arg in enumerate(argv):
        if arg == "--mode" and idx + 1 < len(argv):
            argv[idx + 1] = value
            return
        if arg.startswith("--mode="):
            argv[idx] = f"--mode={value}"
            return
    argv.extend(["--mode", value])


def _drop_arg_with_optional_value(argv: list[str], name: str) -> list[str]:
    out: list[str] = []
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == name:
            idx += 2
            continue
        if arg.startswith(f"{name}="):
            idx += 1
            continue
        out.append(arg)
        idx += 1
    return out


def _set_default_env(key: str, value: str) -> None:
    os.environ.setdefault(key, value)


def _has_read_only_tool_request(argv: list[str]) -> bool:
    return any(arg in READ_ONLY_TOOL_FLAGS for arg in argv)


def _int_arg(argv: list[str], name: str, default: int) -> int:
    try:
        value = _arg_value(argv, name)
        return int(value) if value else default
    except Exception:
        return default


def _float_arg(argv: list[str], name: str, default: float) -> float:
    try:
        value = _arg_value(argv, name)
        return float(value) if value else default
    except Exception:
        return default


def _data_dir_arg(argv: list[str]) -> Path:
    value = _arg_value(argv, "--data-dir")
    return Path(value) if value else Path("data")


def _ensure_project_root_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def _run_read_only_tools(argv: list[str]) -> None:
    _ensure_project_root_on_path()
    data_dir = _data_dir_arg(argv)
    printed = False

    if "--paper-tools" in argv:
        print("PAPER READ-ONLY TOOLS")
        print("  python trading_bot\\avvia_bot_live.py --paper-status")
        print("  python trading_bot\\avvia_bot_live.py --paper-performance")
        print("  python trading_bot\\avvia_bot_live.py --paper-blockers --tail 2000")
        print("  python trading_bot\\avvia_bot_live.py --paper-opportunities --tail 5000")
        print("  python trading_bot\\avvia_bot_live.py --paper-shadow-thresholds --tail 5000")
        print("  python trading_bot\\avvia_bot_live.py --paper-support-rejection --tail 5000")
        print("  python trading_bot\\avvia_bot_live.py --clean-backtest --symbol XRP/USDT --profile active --max-rows 150000")
        print("  python trading_bot\\avvia_bot_live.py --clean-optimize --symbols all --max-rows 150000")
        print("  python trading_bot\\avvia_bot_live.py --clean-cleanup-plan")
        print("  python trading_bot\\avvia_bot_live.py --clean-frequency-audit")
        print("  python trading_bot\\avvia_bot_live.py --clean-download-1m --symbol XRP/USDT --days 90")
        print("  python trading_bot\\avvia_bot_live.py --clean-scalping-1m-audit --symbol XRP/USDT --max-rows 150000")
        print("  python trading_bot\\avvia_bot_live.py --clean-monitor --tail 2000")
        print("  python trading_bot\\avvia_bot_live.py --clean-monitor --tail 2000 --telegram")
        print("  python trading_bot\\avvia_bot_live.py --clean-paper --symbol XRP/USDT --profile active --market-data-mode cache --once")
        print("  python trading_bot\\avvia_bot_live.py --clean-paper --symbol XRP/USDT --profile active --market-data-mode live --poll-seconds 60")
        print("  python trading_bot\\avvia_bot_live.py --clean-paper --telegram-test")
        printed = True

    if "--paper-status" in argv:
        from tools.paper_status_now import build_status_text

        if printed:
            print()
        print(build_status_text(data_dir))
        printed = True

    if "--paper-performance" in argv:
        from tools.paper_performance_report import build_report, format_report

        if printed:
            print()
        print(format_report(build_report(data_dir)))
        printed = True

    if "--paper-blockers" in argv:
        from tools.paper_blocker_report import build_report, format_report

        if printed:
            print()
        print(format_report(build_report(data_dir, tail=_int_arg(argv, "--tail", 2000))))
        printed = True

    if "--paper-opportunities" in argv:
        from tools.paper_strategy_opportunity_audit import build_report, format_report

        if printed:
            print()
        print(format_report(build_report(data_dir, tail=_int_arg(argv, "--tail", 5000))))
        printed = True

    if "--paper-shadow-thresholds" in argv:
        from tools.paper_shadow_threshold_report import build_report, format_report

        if printed:
            print()
        print(format_report(build_report(data_dir, tail=_int_arg(argv, "--tail", 5000))))
        printed = True

    if "--paper-support-rejection" in argv:
        from tools.paper_support_rejection_shadow_report import build_report, format_report

        if printed:
            print()
        print(format_report(build_report(data_dir, tail=_int_arg(argv, "--tail", 5000))))
        printed = True

    if "--clean-backtest" in argv:
        from tools.clean_bot_backtest import format_report
        from trading_bot.clean_bot.backtest import run_backtest
        from trading_bot.clean_bot.models import BacktestSettings
        from trading_bot.clean_bot.strategies import strategy_profile

        if printed:
            print()
        symbol = _arg_value(argv, "--symbol") or "XRP/USDT"
        profile = _arg_value(argv, "--profile") or "conservative"
        settings = BacktestSettings(
            symbol=symbol,
            timeframe=_arg_value(argv, "--timeframe") or "5m",
            starting_balance=_float_arg(argv, "--balance", 100.0),
            risk_per_trade_pct=_float_arg(argv, "--risk-per-trade-pct", 0.005),
            cost_model=_arg_value(argv, "--cost-model") or "conservative",
            max_rows=_int_arg(argv, "--max-rows", 150000),
        )
        report = run_backtest(data_dir=data_dir, settings=settings, strategies=strategy_profile(profile))
        report["profile"] = profile
        print(format_report(report))
        printed = True

    if "--clean-optimize" in argv:
        from tools.clean_bot_optimizer import build_report, format_report, parse_symbols

        if printed:
            print()
        report = build_report(
            data_dir=data_dir,
            symbols=parse_symbols(_arg_value(argv, "--symbols") or "all"),
            timeframe=_arg_value(argv, "--timeframe") or "5m",
            balance=_float_arg(argv, "--balance", 100.0),
            risk_per_trade_pct=_float_arg(argv, "--risk-per-trade-pct", 0.005),
            cost_model=_arg_value(argv, "--cost-model") or "conservative",
            max_rows=_int_arg(argv, "--max-rows", 150000),
        )
        print(format_report(report))
        printed = True

    if "--clean-cleanup-plan" in argv:
        from tools.clean_bot_cleanup_plan import build_report, format_report

        if printed:
            print()
        print(format_report(build_report()))
        printed = True

    if "--clean-frequency-audit" in argv:
        from tools.clean_bot_frequency_audit import SUMMARY, format_report

        if printed:
            print()
        print(format_report(SUMMARY))

    if "--clean-scalping-1m-audit" in argv:
        from tools.clean_bot_scalping_1m_audit import build_report, format_report

        if printed:
            print()
        report = build_report(
            data_dir=data_dir,
            symbol=_arg_value(argv, "--symbol") or "XRP/USDT",
            balance=_float_arg(argv, "--balance", 100.0),
            risk_per_trade_pct=_float_arg(argv, "--risk-per-trade-pct", 0.005),
            max_rows=_int_arg(argv, "--max-rows", 150000),
            slippage_bps=_float_arg(argv, "--slippage-bps", 4.0),
            severe_slippage_bps=_float_arg(argv, "--severe-slippage-bps", 8.0),
            min_trades_per_day=_float_arg(argv, "--min-trades-per-day", 3.0),
            max_trades_per_day=_float_arg(argv, "--max-trades-per-day", 4.5),
            max_drawdown_pct=_float_arg(argv, "--max-drawdown-pct", 25.0),
            top_n=_int_arg(argv, "--top", 10),
        )
        output = Path(_arg_value(argv, "--output") or "data/clean_bot_scalping_1m_audit.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        import json

        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(format_report(report))

    if "--clean-monitor" in argv:
        from tools.clean_bot_monitor_report import build_report, format_report

        if printed:
            print()
        report = build_report(
            data_dir=data_dir,
            tail=_int_arg(argv, "--tail", 2000),
            since_minutes=_float_arg(argv, "--since-minutes", 0.0),
            expected_poll_seconds=_float_arg(argv, "--expected-poll-seconds", 60.0),
        )
        output = Path(_arg_value(argv, "--output") or "data/clean_bot_monitor_report.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        import json

        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        text = format_report(report)
        print(text)
        if "--telegram" in argv:
            from tools.clean_bot_monitor_report import _send_telegram

            result = _send_telegram(text)
            print(f"TELEGRAM_MONITOR ok={result.get('ok')} reason={result.get('reason', '')} status={result.get('status', '')}")


def _prepare_paper_live(argv: list[str]) -> list[str]:
    """Prepare safe paper-live defaults, then delegate to run_paper_trading.

    This is paper-only.  It does not create any live/testnet/exchange broker
    path; those modes remain blocked by this launcher.
    """
    out = list(argv)
    _replace_mode(out, "paper")
    _set_default_env("PYTHONIOENCODING", "utf-8")
    _set_default_env("PYTHONPATH", "trading_bot")
    _set_default_env("PAPER_MODE_ONLY", "1")
    _set_default_env("PAPER_TRADING_ENABLED", "1")
    _set_default_env("PAPER_MARKET_DATA_MODE", "live")
    _set_default_env("PAPER_MAX_POSITIONS", "1")
    _set_default_env("TELEGRAM_POSITION_DASHBOARD_SINGLE_MESSAGE", "1")
    _set_default_env("TELEGRAM_POSITION_DASHBOARD_UPDATE_SECONDS", "20")
    _set_default_env("TELEGRAM_POSITION_DASHBOARD_BAR_WIDTH", "20")
    _set_default_env("LSR_V2_PAPER_SUPERVISED_BRIDGE_OPERATOR_ENABLE", "1")
    _set_default_env("LSR_V2_PAPER_SUPERVISED_BRIDGE_CONFIRM", "I_UNDERSTAND_LSR_V2_PAPER_SUPERVISED_ONLY")
    _set_default_env("LSR_V2_PAPER_SUPERVISED_SUBMIT_ENABLE", "1")
    _set_default_env("LSR_V2_PAPER_SUPERVISED_SUBMIT_CONFIRM", "I_UNDERSTAND_PAPER_ONLY")
    _set_default_env("PAPER_ORDER_LEAKAGE_GUARD_ALLOW_SUPERVISED", "1")
    _set_default_env("PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE", "1")
    _set_default_env("PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM", "I_UNDERSTAND_PAPER_ONLY")
    _ensure_arg(out, "--market-data-mode", "live")
    _ensure_arg(out, "--max-positions", "1")
    _ensure_arg(out, "--risk-per-trade-pct", "0.0025")
    _ensure_arg(out, "--paper-unlock-profile", "BTC_ONLY_40_Q60")
    _ensure_arg(out, "--paper-unlock-supervised-confirm", "I_UNDERSTAND_PAPER_ONLY")
    for flag in (
        "--paper-unlock",
        "--paper-unlock-supervised-execution",
        "--lsr-v2-bridge-operator-enable",
        "--telegram-proactive",
    ):
        if flag not in out:
            out.append(flag)
    _ensure_arg(out, "--lsr-v2-bridge-confirm", "I_UNDERSTAND_LSR_V2_PAPER_SUPERVISED_ONLY")
    return out


def _emit_lsr_v2_read_only_banner() -> None:
    if emit_lsr_v2_launcher_read_only_dashboard_banner is None:
        print("[LSR-V2 LAUNCHER DASHBOARD] unavailable read-only fail-closed")
        return
    try:
        emit_lsr_v2_launcher_read_only_dashboard_banner(data_dir="data")
    except Exception as exc:  # pragma: no cover - defensive; never change launcher execution mode
        print(f"[LSR-V2 LAUNCHER DASHBOARD] unavailable read-only fail-closed: {exc}")


def main() -> None:
    argv = sys.argv[1:]
    if _live_requested(argv):
        raise SystemExit("Live/testnet real-money execution is disabled. Use --mode paper or --mode paper-live.")
    if "--clean-download-1m" in argv:
        _ensure_project_root_on_path()
        tool_argv = [arg for arg in argv if arg != "--clean-download-1m"]
        sys.argv = [sys.argv[0], *tool_argv]
        from tools.clean_bot_download_1m import main as clean_download_main

        raise SystemExit(clean_download_main())
    if _has_read_only_tool_request(argv):
        _run_read_only_tools(argv)
        return
    mode = _arg_value(argv, "--mode").strip().lower()
    if "--clean-paper" in argv or mode == "clean-paper":
        _ensure_project_root_on_path()
        clean_argv = [arg for arg in argv if arg != "--clean-paper"]
        clean_argv = _drop_arg_with_optional_value(clean_argv, "--mode")
        sys.argv = [sys.argv[0], *clean_argv]
        from tools.clean_bot_paper_live import main as clean_paper_main

        raise SystemExit(clean_paper_main())
    if mode == "paper-live":
        argv = _prepare_paper_live(argv)
        sys.argv = [sys.argv[0], *argv]
    _emit_lsr_v2_read_only_banner()
    from run_paper_trading import main as paper_main

    paper_main()


if __name__ == "__main__":
    main()
