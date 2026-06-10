from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _open_positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    positions = state.get("positions")
    if isinstance(positions, dict):
        rows = [p for p in positions.values() if isinstance(p, dict)]
    elif isinstance(positions, list):
        rows = [p for p in positions if isinstance(p, dict)]
    else:
        rows = []
    return [p for p in rows if str(p.get("status") or "").upper() == "OPEN"]


def _mark_price(position: dict[str, Any], status: dict[str, Any]) -> float:
    symbol = str(position.get("symbol") or "")
    last_prices = status.get("last_prices")
    if isinstance(last_prices, dict) and symbol in last_prices:
        return _safe_float(last_prices.get(symbol), _safe_float(position.get("entry_price")))
    paper_monitor = status.get("paper_position_monitor")
    if isinstance(paper_monitor, dict):
        by_symbol = paper_monitor.get(symbol)
        if isinstance(by_symbol, dict):
            return _safe_float(by_symbol.get("mark_price"), _safe_float(position.get("entry_price")))
    return _safe_float(position.get("mark_price"), _safe_float(position.get("entry_price")))


def _pnl(position: dict[str, Any], mark: float) -> tuple[float, float]:
    side = str(position.get("side") or "").upper()
    qty = abs(_safe_float(position.get("qty")))
    entry = _safe_float(position.get("entry_price"))
    if side == "SELL":
        pnl = qty * (entry - mark)
    else:
        pnl = qty * (mark - entry)
    notional = abs(qty * entry) or 1.0
    return pnl, pnl / notional * 100.0


def _distance(position: dict[str, Any], mark: float) -> tuple[float, float]:
    tp = _safe_float(position.get("take_profit"))
    sl = _safe_float(position.get("stop_loss"))
    return abs(tp - mark) if tp > 0 else 0.0, abs(mark - sl) if sl > 0 else 0.0


def build_status_text(data_dir: Path) -> str:
    state = _read_json(data_dir / "paper_state.json")
    status = _read_json(data_dir / "paper_status.json")
    telegram_state = _read_json(data_dir / "telegram_proactive_state.json")
    positions = _open_positions(state)
    lines = [
        "PAPER STATUS NOW",
        f"mode={status.get('mode') or 'paper'}",
        f"equity={_safe_float(status.get('equity'), _safe_float(state.get('balance'))):.2f}",
        f"balance={_safe_float(state.get('balance')):.2f}",
        f"realized_pnl={_safe_float(state.get('realized_pnl')):+.2f}",
        f"open_positions={len(positions)}",
    ]
    if not positions:
        lines.append("state=FLAT")
    for pos in positions:
        mark = _mark_price(pos, status)
        pnl, pnl_pct = _pnl(pos, mark)
        dist_tp, dist_sl = _distance(pos, mark)
        pid = str(pos.get("position_id") or "")
        msg_ids = telegram_state.get("live_position_message_id_by_position")
        msg_id = msg_ids.get(pid) if isinstance(msg_ids, dict) else None
        lines.extend([
            "",
            f"position_id={pid}",
            f"symbol={pos.get('symbol')}",
            f"side={pos.get('side')}",
            f"entry={_safe_float(pos.get('entry_price')):.2f}",
            f"mark={mark:.2f}",
            f"qty={_safe_float(pos.get('qty')):.8f}",
            f"stop_loss={_safe_float(pos.get('stop_loss')):.2f}",
            f"take_profit={_safe_float(pos.get('take_profit')):.2f}",
            f"distance_tp={dist_tp:.2f}",
            f"distance_sl={dist_sl:.2f}",
            f"unrealized_pnl={pnl:+.2f}",
            f"unrealized_pnl_pct={pnl_pct:+.2f}%",
            f"telegram_dashboard_message_id={msg_id or '-'}",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print current paper trading state in a terminal-friendly format.")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    print(build_status_text(Path(args.data_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
