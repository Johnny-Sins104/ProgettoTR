"""
Regression tests for risk-event/dashboard consistency.

These tests cover the bug where the backtest created zero-size trades after
risk blocking, while the DynamicRiskEngine dashboard counted only one
risk-bearing sizing snapshot.  The expected behavior is:
  - blocked/zero-size attempts are not emitted as closed trades;
  - closed trade events are canonical and carry realized_pnl;
  - dashboard diagnostics count risk-bearing snapshots consistently.
"""

from core.risk import DynamicRiskEngine


def test_record_trade_event_uses_balance_delta_when_trade_pnl_is_zero():
    engine = DynamicRiskEngine(initial_balance=1_000.0, daily_loss_limit_pct=99.0)
    size, snapshot = engine.size_position(
        balance=1_000.0,
        entry_price=100.0,
        sl_price=95.0,
        side="BUY",
        regime="TRENDING",
        ai_prob=70.0,
        rr_ratio=2.0,
        atr_val=2.0,
        base_risk_pct=0.02,
    )
    assert size > 0

    engine.record_trade_event(
        {"side": "BUY", "result": "WIN", "entry": 100.0, "exit": 104.0, "pnl": 0.0},
        balance_before=1_000.0,
        balance_after=1_025.0,
    )

    assert len(engine.trade_events) == 1
    assert engine.trade_events[0]["realized_pnl"] == 25.0
    assert engine.compute_diagnostics().n_snapshots == 1


def test_blocked_sizing_snapshot_is_not_counted_as_risk_bearing_trade():
    engine = DynamicRiskEngine(initial_balance=1_000.0, daily_loss_limit_pct=1.0)
    engine.update_equity(980.0)  # daily loss > 1%, new trades blocked

    size, snapshot = engine.size_position(
        balance=980.0,
        entry_price=100.0,
        sl_price=95.0,
        side="BUY",
        regime="RANGING",
        ai_prob=60.0,
        rr_ratio=2.0,
        atr_val=2.0,
        base_risk_pct=0.02,
    )

    assert snapshot.daily_loss_blocked is True
    assert size == 0.0
    assert len(engine.risk_log) == 1
    assert engine.compute_diagnostics().n_snapshots == 0
    assert len(engine.trade_events) == 0


if __name__ == "__main__":
    test_record_trade_event_uses_balance_delta_when_trade_pnl_is_zero()
    test_blocked_sizing_snapshot_is_not_counted_as_risk_bearing_trade()
    print("Risk dashboard consistency tests passed.")
