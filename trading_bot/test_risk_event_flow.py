"""Risk event-flow smoke tests for the backtest/risk integration patch.

These tests cover the failure mode observed in the live backtest dashboard:
closed trades existed, but the DynamicRiskEngine reported "Trades analysed: 0".
"""

from core.risk import DynamicRiskEngine


def test_risk_engine_records_sizing_and_close_event():
    engine = DynamicRiskEngine(initial_balance=1_000.0, max_leverage=8.0)

    size, snap = engine.size_position(
        balance=1_000.0,
        entry_price=100.0,
        sl_price=98.0,
        side="BUY",
        regime="TRENDING",
        ai_prob=62.0,
        rr_ratio=2.0,
        atr_val=1.5,
        base_risk_pct=0.03,
        commission=0.0002,
    )

    assert size > 0.0
    assert snap.final_risk_pct > 0.0
    assert snap.effective_leverage > 0.0
    assert len(engine.risk_log) == 1

    trade = {
        "side": "BUY",
        "result": "WIN",
        "entry": 100.0,
        "tp": 104.0,
        "pnl": 15.0,
        "balance": 1_015.0,
        "regime": "TRENDING",
        "ai_prob": 62.0,
    }
    engine.record_trade_event(trade, balance_before=1_000.0, balance_after=1_015.0)

    assert len(engine.trade_events) == 1
    assert engine.compute_diagnostics().n_snapshots == 1
    assert engine.compute_diagnostics().avg_leverage > 0.0
    assert engine.trade_events[0]["pnl"] == 15.0


if __name__ == "__main__":
    test_risk_engine_records_sizing_and_close_event()
    print("Risk event-flow smoke test passed.")
