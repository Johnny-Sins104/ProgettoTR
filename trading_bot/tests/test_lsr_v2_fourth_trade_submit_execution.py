from __future__ import annotations

from core.lsr_v2_fourth_trade_submit_execution import (
    PASS_DECISION,
    ENV_INVALID_DECISION,
    FAILED_DECISION,
    build_lsr_v2_fourth_trade_submit_execution_report,
)


def _flat_state():
    return {"balance": 1023.75, "realized_pnl": 23.75, "positions": {}, "orders": {}}


def _flat_status():
    return {"open_positions": 0, "pending_orders": 0, "balance": 1023.75, "realized_pnl": 23.75}


def _source_ok():
    return {
        "submit_execution_source_files_present": True,
        "submit_execution_required_markers_present": True,
        "missing_submit_execution_source_files": [],
        "missing_submit_execution_source_markers": {},
    }


def _base_t16(**overrides):
    data = {
        "status": "PASS",
        "decision": "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY",
        "submit_preflight_ready": True,
        "route_preflight_ready": True,
        "handoff_dry_run_ready": True,
        "route_candidate_available": False,
        "would_route": False,
        "would_create_order": False,
        "paper_order_intent_ready": False,
        "paper_order_intent": {},
        "would_submit": False,
        "submit_blocked_reason": "no_route_candidate_available",
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_trade_allowed": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "aggregate_realized_pnl": 23.7543,
        "lifecycle_state": "FLAT_LOCKED",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
    }
    data.update(overrides)
    return data


def test_no_order_intent_passes_fail_closed_no_submit():
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=_base_t16(),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["submit_execution_ready"] is True
    assert report["paper_order_intent_ready"] is False
    assert report["submit_execution_diagnostic"] == "NO_ORDER_SUBMIT_EXECUTION_DIAGNOSTIC"
    assert report["would_submit"] is False
    assert report["broker_submit_called"] is False
    assert report["broker_submit_called_by_submit_execution"] is False
    assert report["orders_submitted_by_submit_execution"] == 0
    assert report["positions_opened_by_submit_execution"] == 0
    assert report["paper_state_modified_by_submit_execution"] is False


def test_order_intent_without_operator_controls_warns_and_does_not_submit():
    preflight = _base_t16(
        route_candidate_available=True,
        would_route=True,
        would_create_order=True,
        paper_order_intent_ready=True,
        paper_order_intent={"symbol": "BTC/USDT", "side": "BUY", "quantity": 0.01},
    )
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=preflight,
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_INVALID_DECISION
    assert report["paper_order_intent_ready"] is True
    assert report["submit_execution_operator_controls_valid"] is False
    assert report["would_submit"] is False
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_submit_execution"] == 0


def test_order_intent_with_controls_still_scaffold_only_no_broker_call():
    preflight = _base_t16(
        route_candidate_available=True,
        would_route=True,
        would_create_order=True,
        paper_order_intent_ready=True,
        paper_order_intent={"symbol": "ETH/USDT", "side": "BUY", "quantity": 0.25},
    )
    env = {
        "LSR_V2_FOURTH_TRADE_REARM_ENABLE": "1",
        "LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION": "I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY",
        "LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS": "1",
    }
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=preflight,
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map=env,
    )
    assert report["status"] == "PASS"
    assert report["submit_execution_operator_controls_valid"] is True
    assert report["submit_execution_would_submit_if_execution_patch_enabled"] is True
    assert report["would_submit"] is False
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_submit_execution"] == 0


def test_live_flag_fails_hard():
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=_base_t16(live_enabled=True),
        paper_state=_flat_state(),
        paper_status=_flat_status(),
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
    assert report["orders_submitted_by_submit_execution"] == 0


def test_not_flat_warns_and_does_not_submit():
    state = {"positions": {"p1": {"status": "OPEN"}}, "orders": {}, "balance": 1000}
    report = build_lsr_v2_fourth_trade_submit_execution_report(
        submit_preflight=_base_t16(),
        paper_state=state,
        paper_status={"open_positions": 1, "pending_orders": 0},
        source_audit=_source_ok(),
        env_map={},
    )
    assert report["status"] == "WARN"
    assert report["paper_state_modified_by_submit_execution"] is False
    assert report["positions_opened_by_submit_execution"] == 0
