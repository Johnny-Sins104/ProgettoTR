from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.clean_bot.data import SYMBOL_CACHE_NAMES, load_ohlcv
from trading_bot.clean_bot.indicators import add_indicators
from trading_bot.clean_bot.validation_gates import oos_with_warmup, temporal_concentration_check
from trading_bot.core.unified_trade_cost import UnifiedCostModel


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _ucm_scenario(cost_model: str) -> str:
    return {"base": "realistic"}.get(cost_model, cost_model)


def _candidate_grid() -> list[dict[str, Any]]:
    return [
        {"lookback_bars": 576, "volume_min": 1.5, "stop_atr_mult": 4.0, "trail_atr_mult": 10.0, "max_hold_bars": 1728},
        {"lookback_bars": 576, "volume_min": 1.5, "stop_atr_mult": 4.0, "trail_atr_mult": 6.0, "max_hold_bars": 1728},
        {"lookback_bars": 576, "volume_min": 1.0, "stop_atr_mult": 4.0, "trail_atr_mult": 10.0, "max_hold_bars": 1728},
        {"lookback_bars": 576, "volume_min": 1.5, "stop_atr_mult": 6.0, "trail_atr_mult": 10.0, "max_hold_bars": 1728},
        {"lookback_bars": 1152, "volume_min": 1.5, "stop_atr_mult": 4.0, "trail_atr_mult": 10.0, "max_hold_bars": 1728},
        {"lookback_bars": 1152, "volume_min": 1.0, "stop_atr_mult": 4.0, "trail_atr_mult": 10.0, "max_hold_bars": 1728},
    ]


def _run_candidate(
    df,
    *,
    params: dict[str, Any],
    balance: float,
    risk_per_trade_pct: float,
    cost_model: str,
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    start: int = 0,
    end: int | None = None,
) -> dict[str, Any]:
    frame = df.iloc[start:end].reset_index(drop=True)
    has_datetime = "datetime" in frame.columns
    lookback = int(params["lookback_bars"])
    prior_high_col = f"prior_high_{lookback}"
    lows = frame["Low"].to_numpy()
    closes = frame["Close"].to_numpy()
    opens = frame["Open"].to_numpy()
    ema50 = frame["ema50"].to_numpy()
    ema200 = frame["ema200"].to_numpy()
    atr = frame["atr14"].to_numpy()
    atr_pct = frame["atr_pct"].to_numpy()
    volume_ratio = frame["volume_ratio_20"].to_numpy()
    prior_high = frame[prior_high_col].to_numpy()
    equity = float(balance)
    peak = equity
    max_dd = 0.0
    pnls: list[float] = []
    r_values: list[float] = []
    trades: list[dict[str, Any]] = []
    idx = max(401, lookback + 1)
    scenario = _ucm_scenario(cost_model)
    while idx < len(frame) - 2:
        close = float(closes[idx])
        if (
            close > float(prior_high[idx])
            and close > float(ema50[idx]) > float(ema200[idx])
            and float(volume_ratio[idx]) >= float(params["volume_min"])
            and 0.03 <= float(atr_pct[idx]) <= 1.50
        ):
            entry_idx = idx + 1
            entry_price = float(opens[entry_idx])
            stop_price = close - float(atr[idx]) * float(params["stop_atr_mult"])
            risk_per_unit = abs(entry_price - stop_price)
            qty = min((equity * risk_per_trade_pct) / risk_per_unit, equity / entry_price) if risk_per_unit > 0 else 0.0
            if qty <= 0:
                idx += 1
                continue
            trailing_stop = stop_price
            exit_idx = entry_idx
            exit_price = float(closes[entry_idx])
            end_idx = min(len(frame) - 1, entry_idx + int(params["max_hold_bars"]))
            for pos in range(entry_idx, end_idx + 1):
                if float(lows[pos]) <= trailing_stop:
                    exit_idx = pos
                    exit_price = trailing_stop
                    break
                trailing_stop = max(trailing_stop, float(closes[pos]) - float(atr[pos]) * float(params["trail_atr_mult"]))
                exit_idx = pos
                exit_price = float(closes[pos])
            gross_pnl = qty * (exit_price - entry_price)
            actual_risk = max(0.00000001, qty * risk_per_unit)
            atr_pct_val = float(atr_pct[idx])
            _cost_result = UnifiedCostModel.apply_cost_to_backtest_trade(
                gross_pnl=gross_pnl,
                initial_risk=actual_risk,
                entry_price=entry_price,
                exit_price=max(1e-8, exit_price),
                quantity=qty,
                scenario=scenario,
                symbol=symbol,
                timeframe=timeframe,
                atr_pct=atr_pct_val,
            )
            net_pnl = _cost_result["net_pnl"]
            pnls.append(net_pnl)
            r_values.append(net_pnl / actual_risk)
            entry_time = str(frame.iloc[entry_idx]["datetime"]) if has_datetime else ""
            trades.append({"net_pnl": net_pnl, "entry_time": entry_time})
            equity += net_pnl
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            idx = exit_idx + 1
            continue
        idx += 1
    gross_profit = sum(max(0.0, pnl) for pnl in pnls)
    gross_loss = sum(abs(min(0.0, pnl)) for pnl in pnls)
    return {
        "closed_trades": len(pnls),
        "return_pct": (equity - balance) / balance * 100.0 if balance else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "win_rate_pct": sum(1 for pnl in pnls if pnl > 0) / len(pnls) * 100.0 if pnls else 0.0,
        "max_drawdown_pct": max_dd,
        "average_r": sum(r_values) / len(r_values) if r_values else 0.0,
        "trades": trades,
    }


def _paper_eligible(full: dict[str, Any], oos: dict[str, Any]) -> bool:
    oos_pf = _float(oos.get("profit_factor"))
    if not (
        oos["closed_trades"] >= 50
        and oos["return_pct"] > 0.0
        and oos_pf > 1.00
    ):
        return False
    oos_trades = oos.get("trades") or []
    if not oos_trades:
        return False
    tc = temporal_concentration_check(oos_trades)
    return tc["passes"]


def build_report(
    *,
    data_dir: Path,
    symbols: list[str],
    timeframe: str,
    balance: float,
    risk_per_trade_pct: float,
    cost_model: str,
    max_rows: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        raw = load_ohlcv(data_dir, symbol, timeframe, max_rows)
        df = add_indicators(raw).dropna().reset_index(drop=True)

        # Replace second-half split with a true OOS gate (no-lookahead)
        oos_df, warmup_count = oos_with_warmup(df)
        train_end = len(df) - (len(oos_df) - warmup_count)

        symbol_rows: list[dict[str, Any]] = []
        for params in _candidate_grid():
            full = _run_candidate(
                df, params=params, balance=balance, risk_per_trade_pct=risk_per_trade_pct,
                cost_model=cost_model, symbol=symbol, timeframe=timeframe,
            )
            train = _run_candidate(
                df, params=params, balance=balance, risk_per_trade_pct=risk_per_trade_pct,
                cost_model=cost_model, symbol=symbol, timeframe=timeframe, end=train_end,
            )
            oos = _run_candidate(
                oos_df, params=params, balance=balance, risk_per_trade_pct=risk_per_trade_pct,
                cost_model=cost_model, symbol=symbol, timeframe=timeframe,
            )
            score = train["return_pct"]
            symbol_rows.append(
                {
                    "symbol": symbol,
                    "strategy": "adaptive_trend_breakout",
                    "params": params,
                    "score": score,
                    "status": "PAPER_CANDIDATE" if _paper_eligible(full, oos) else "RESEARCH_ONLY",
                    "full": full,
                    "train": train,
                    "oos": oos,
                }
            )
        symbol_rows.sort(key=lambda row: row["score"], reverse=True)
        results.extend(symbol_rows[:5])
    candidates = [row for row in results if row["status"] == "PAPER_CANDIDATE"]
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return {
        "report_type": "clean_bot_optimizer",
        "diagnostic_only": True,
        "opens_orders": False,
        "settings": {
            "symbols": symbols,
            "timeframe": timeframe,
            "balance": balance,
            "risk_per_trade_pct": risk_per_trade_pct,
            "cost_model": cost_model,
            "max_rows": max_rows,
            "oos_gate": "oos_with_warmup",
        },
        "candidate_count": len(candidates),
        "paper_candidates": candidates,
        "top_by_symbol": results,
    }


def _fmt_pf(value: Any) -> str:
    return "-" if value is None else f"{_float(value):.3f}"


def format_report(report: dict[str, Any]) -> str:
    settings = report["settings"]
    lines = [
        "CLEAN BOT OPTIMIZER",
        f"symbols={','.join(settings['symbols'])} timeframe={settings['timeframe']} cost={settings['cost_model']} rows={settings['max_rows']}",
        f"balance={settings['balance']:.2f} risk_per_trade={settings['risk_per_trade_pct'] * 100:.2f}%",
        f"oos_gate={settings.get('oos_gate', 'oos_with_warmup')} paper_candidates={report['candidate_count']}",
        "",
    ]
    if report["paper_candidates"]:
        lines.append("paper_candidates:")
        for row in report["paper_candidates"]:
            full = row["full"]
            oos = row["oos"]
            params = row["params"]
            lines.append(
                f"  {row['symbol']}: full_return={full['return_pct']:+.2f}% pf={_fmt_pf(full['profit_factor'])} "
                f"oos_return={oos['return_pct']:+.2f}% oos_pf={_fmt_pf(oos['profit_factor'])} "
                f"trades={full['closed_trades']} params={params}"
            )
        lines.append("")
    lines.append("top_by_symbol:")
    for row in report["top_by_symbol"]:
        full = row["full"]
        train = row["train"]
        oos = row["oos"]
        params = row["params"]
        lines.append(
            f"  {row['symbol']} {row['status']}: score={row['score']:+.2f} "
            f"full={full['return_pct']:+.2f}%/{_fmt_pf(full['profit_factor'])} "
            f"train={train['return_pct']:+.2f}% oos={oos['return_pct']:+.2f}% params={params}"
        )
    return "\n".join(lines)


def parse_symbols(value: str) -> list[str]:
    if value.strip().lower() in {"all", "*"}:
        return sorted(SYMBOL_CACHE_NAMES)
    return [item.strip().upper().replace("USDT", "/USDT") if "/" not in item.strip().upper() else item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize clean bot strategy candidates read-only.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--symbols", default="all")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--balance", type=float, default=100.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--max-rows", type=int, default=150000)
    parser.add_argument("--output", default="data/clean_bot_optimizer_report.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(
        data_dir=Path(args.data_dir),
        symbols=parse_symbols(args.symbols),
        timeframe=args.timeframe,
        balance=args.balance,
        risk_per_trade_pct=args.risk_per_trade_pct,
        cost_model=args.cost_model,
        max_rows=args.max_rows,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
