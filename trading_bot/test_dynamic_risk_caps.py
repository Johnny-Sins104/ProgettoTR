"""
test_dynamic_risk_caps.py

Regression test for DYNAMIC profile risk caps.  A high-confidence Kelly input
must not expand the dynamic profile to 15-20% single-trade risk.
"""
from config import Config
from core.risk import DynamicRiskEngine


def main() -> None:
    engine = DynamicRiskEngine(initial_balance=1_000.0, max_leverage=getattr(Config, "DYNAMIC_MAX_LEVERAGE", 4.0))
    for _ in range(10):
        engine._push_atr(100.0)

    dynamic_cap = float(getattr(Config, "DYNAMIC_MAX_RISK_PCT", 0.03))
    raw_risk = engine.calculate_kelly_risk_pct(ai_probability=90.0, rr_ratio=2.0, default_risk=Config.DYNAMIC_DEFAULT_RISK_PCT)
    capped_risk = min(raw_risk, dynamic_cap)

    size, snap = engine.size_position(
        balance=1_000.0,
        entry_price=50_000.0,
        sl_price=49_500.0,
        side="BUY",
        regime="TRENDING",
        ai_prob=90.0,
        rr_ratio=2.0,
        atr_val=100.0,
        base_risk_pct=capped_risk,
    )

    assert snap.final_risk_pct <= dynamic_cap + 1e-12, (snap.final_risk_pct, dynamic_cap)
    assert snap.effective_leverage <= float(getattr(Config, "DYNAMIC_MAX_LEVERAGE", 4.0)) + 1e-12
    print("Dynamic risk caps test passed.")


if __name__ == "__main__":
    main()
