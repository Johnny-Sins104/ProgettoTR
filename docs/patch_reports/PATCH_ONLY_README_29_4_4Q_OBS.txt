ProgettoTR patch-only package
Patch: 29.4.4q-OBS — 4h audit-only observation run

Extract this ZIP into the root folder:
C:\Users\Davide\Desktop\ProgettoTR-main

Overwrite files when asked.

This patch assumes 29.4.4q is already installed and validated.

Files included:
- trading_bot/core/paper_unlock_observation.py
- trading_bot/run_paper_unlock_4h_observation.py
- trading_bot/test_paper_unlock_observation.py
- trading_bot/config.py
- docs/patch_reports/PROMPT_29_4_4Q_OBS_PATCH_REPORT.md
- trading_bot/docs/patch_reports/PROMPT_29_4_4Q_OBS_PATCH_REPORT.md

Smoke test:
python trading_bot\test_paper_unlock_observation.py
python trading_bot\run_paper_unlock_4h_observation.py --duration-hours 0.05 --interval-seconds 60 --max-cycles 1

Full 4h observation:
python trading_bot\run_paper_unlock_4h_observation.py --duration-hours 4 --interval-seconds 300

Report-only:
python trading_bot\run_paper_unlock_4h_observation.py --report-only

Safety unchanged:
NO live
NO testnet
NO exchange broker reale
NO order submission
NO position opening
NO risk/gate/signal/routing changes
