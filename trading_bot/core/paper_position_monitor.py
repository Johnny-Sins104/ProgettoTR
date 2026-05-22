"""Prompt 29.4a paper position monitor utilities.

The monitor restores the old live-like operator view in a paper-safe form.  It
uses adapter snapshots only; it does not place, modify or close orders.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json

from core.broker_adapter import AccountSnapshot, PositionSnapshot, utc_now_iso


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _fmt_qty(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _fmt_money(value: float) -> str:
    return f"{float(value):+.2f}"


class PaperPositionMonitor:
    def __init__(self, *, output_path: str | Path = "data/paper_position_monitor.json") -> None:
        self.output_path = Path(output_path)

    def build_payload(self, *, account: AccountSnapshot, positions: list[PositionSnapshot]) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "mode": "paper",
            "account": asdict(account),
            "open_position_count": len(positions),
            "positions": [asdict(p) for p in positions],
            "status": "ACTIVE" if positions else "FLAT",
        }

    def write(self, *, account: AccountSnapshot, positions: list[PositionSnapshot]) -> dict[str, Any]:
        payload = self.build_payload(account=account, positions=positions)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def format_console(self, *, account: AccountSnapshot, positions: list[PositionSnapshot]) -> str:
        if not positions:
            return ""
        blocks = [self._format_position(account=account, position=p) for p in positions]
        return "\n\n".join(blocks)

    def format_telegram(self, *, account: AccountSnapshot, positions: list[PositionSnapshot]) -> str:
        if not positions:
            return "No open paper positions."
        blocks = [self._format_position(account=account, position=p) for p in positions]
        return "\n\n".join(blocks)[:3900]

    def _format_position(self, *, account: AccountSnapshot, position: PositionSnapshot) -> str:
        direction = "BUY/LONG" if str(position.side).upper() == "BUY" else "SELL/SHORT"
        reason = position.reason or "-"
        tp1_state = "✅ HIT" if self._target_hit(position, position.take_profit_1) else "⏳ PENDING"
        tp2_state = "✅ HIT" if self._target_hit(position, position.take_profit_2) else "⏳ PENDING"
        sl_state = "⚠️ TOUCHED" if self._stop_touched(position) else "⏳ ARMED"
        return (
            "📈 PAPER POSITION MONITOR\n"
            "==============================\n"
            f"Symbol   : {position.symbol}\n"
            f"Direzione: {direction}\n"
            f"Motivo   : {reason}\n"
            f"Ingresso : {_fmt_price(position.entry_price)} USDT\n"
            f"Attuale  : {_fmt_price(position.mark_price)} USDT\n"
            f"Size     : {_fmt_qty(position.qty)}\n"
            f"Margine  : {position.margin_estimate:.2f} USDT-equivalent\n"
            "==============================\n"
            f"TP1      : {_fmt_price(position.take_profit_1)} USDT {tp1_state}\n"
            f"TP2      : {_fmt_price(position.take_profit_2)} USDT {tp2_state}\n"
            f"SL       : {_fmt_price(position.stop_loss)} USDT {sl_state}\n"
            "==============================\n"
            f"PnL Att. : {_fmt_money(position.unrealized_pnl)} USDT ({position.unrealized_pnl_pct:+.2f}%)\n"
            f"Equity   : {account.equity:.2f} USDT-equivalent\n"
            "=============================="
        )

    def _target_hit(self, position: PositionSnapshot, target: float | None) -> bool:
        if target is None:
            return False
        if str(position.side).upper() == "BUY":
            return position.mark_price >= target
        return position.mark_price <= target

    def _stop_touched(self, position: PositionSnapshot) -> bool:
        if position.stop_loss is None:
            return False
        if str(position.side).upper() == "BUY":
            return position.mark_price <= position.stop_loss
        return position.mark_price >= position.stop_loss
