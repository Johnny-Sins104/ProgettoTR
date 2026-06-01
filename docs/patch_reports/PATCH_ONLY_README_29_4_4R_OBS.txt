ProgettoTR patch-only package
Patch: 29.4.4r-OBS — 8h audit/dry-run observation

Apply on top of a local tree already updated through validated 29.4.4r.

Files included:
- trading_bot/core/paper_unlock_observation.py
- trading_bot/run_paper_unlock_4h_observation.py
- trading_bot/run_paper_unlock_8h_observation.py
- trading_bot/test_paper_unlock_observation.py
- docs/patch_reports/PROMPT_29_4_4R_OBS_PATCH_REPORT.md
- trading_bot/docs/patch_reports/PROMPT_29_4_4R_OBS_PATCH_REPORT.md

Smoke test after extraction:
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\test_paper_unlock_observation.py
python trading_bot\run_paper_unlock_8h_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1

Full 8h run:
python trading_bot\run_paper_unlock_8h_observation.py --duration-hours 8 --interval-seconds 300

Final report:
data\paper_unlock_8h_dry_run_observation_report.json

Safety: audit/dry-run only. No live, no testnet, no exchange broker, no order submission, no position opening, no gate/risk/signal/routing changes.
