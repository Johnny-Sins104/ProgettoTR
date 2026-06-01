Prompt 29.4.4s-1 — Signal/Risk Correctness Hardening

Patch-only package. Extract into the project root.

This patch fixes/guards:
- conflicting candlestick directional patterns;
- permissive engulfing;
- current-candle volume look-ahead;
- calibration sample thresholds;
- Kelly negative-edge fallback to profile risk;
- PaperBroker/Kelly fee mismatch;
- hardcoded paper unlock profile;
- VaR off-by-one in concentration flags;
- live exit fee price accounting;
- near_sr support/resistance double activation;
- JSONL full-file rereads in paper diagnostics;
- probability compression/zero-trade diagnostics.

No live/testnet/exchange broker enablement is introduced.
No thresholds are lowered to force trades.

Recommended validation:
python -m compileall -q trading_bot
python trading_bot\test_signal_risk_correctness_hardening.py
python trading_bot\test_runtime_risk_io_hardening.py
python trading_bot\test_probability_compression_diagnostic.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\run_probability_compression_diagnostic.py
