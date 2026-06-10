from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BacktestSettings:
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    starting_balance: float = 100.0
    risk_per_trade_pct: float = 0.005
    max_daily_loss_pct: float = 0.03
    max_positions: int = 1
    max_hold_bars: int = 36
    cost_model: str = "conservative"
    max_rows: int = 50000
    # Opt-in perpetual funding accrual (clean_bot/funding.py). When True,
    # run_backtest_frame requires an explicit funding_df (fail-closed pairing).
    funding_enabled: bool = False


@dataclass(frozen=True)
class Signal:
    strategy: str
    side: str
    score: float
    reason: str
    stop_price: float
    take_profit: float
    metadata: dict[str, Any]


@dataclass
class Trade:
    strategy: str
    symbol: str
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit: float
    qty: float
    gross_pnl: float
    cost: float
    net_pnl: float
    r_multiple: float
    exit_reason: str
    bars_held: int
    signal_reason: str
    # TR-INT-02 audit fields (optional, None = not populated)
    signal_price: float | None = None
    fill_price: float | None = None
    entry_timing: str | None = None  # "open_n1" for backtest
    gap_flag: str | None = None      # "SL_GAP" / "TP_GAP" when gap triggered exit
    cost_bps_applied: float | None = None  # total_round_trip_bps from UnifiedCostModel
    # Funding accrual fields (populated only when settings.funding_enabled).
    # Funding is a PnL accrual, never mixed into cost or net_pnl.
    funding_pnl: float | None = None
    funding_events: int | None = None
    net_pnl_with_funding: float | None = None  # net_pnl + funding_pnl

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_entry_price(entry_price: float, signal: "Signal") -> tuple[bool, str]:
    """Shared entry-gap validation for both paper and backtest.

    Returns (True, "OK") if the entry is causally valid.
    Returns (False, reason) if the entry has already gapped through SL or TP and must be rejected.

    BUY: entry must be strictly above stop and strictly below take_profit.
    SELL: entry must be strictly below stop and strictly above take_profit.
    """
    stop = float(signal.stop_price)
    tp = float(signal.take_profit)
    side = str(signal.side).upper()
    if side == "BUY":
        if entry_price <= stop:
            return False, "ENTRY_AT_OR_BELOW_SL"
        if tp > 0 and entry_price >= tp:
            return False, "ENTRY_AT_OR_ABOVE_TP"
    elif side == "SELL":
        if entry_price >= stop:
            return False, "ENTRY_AT_OR_ABOVE_SL"
        if tp > 0 and entry_price <= tp:
            return False, "ENTRY_AT_OR_BELOW_TP"
    return True, "OK"
