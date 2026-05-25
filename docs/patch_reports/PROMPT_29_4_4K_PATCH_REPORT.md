# Prompt 29.4.4k — Manual paper-only switch dry-run / fail-closed preflight

## Stato

Patch diagnostica-only. Non abilita ordini, paper orders, testnet, live, exchange broker, attivazione automatica o attivazione manuale in questa patch.

## Scopo

La 29.4.4j ha prodotto il contratto di switch manuale paper-only. La 29.4.4k aggiunge un preflight dry-run/fail-closed che verifica:

- switch draft 29.4.4j presente e pronto;
- selected entries >= 20;
- cadence richiesta `bounded_6_daily_30_weekly_0h`;
- profilo `MAP_SCORE_65_79_REPAIRED_STABILITY_V1`;
- due-step manual confirmation;
- blocco se manca env manuale;
- blocco se confirm non corrisponde;
- blocco se mode live/testnet;
- blocco se exchange broker non è `blocked`;
- anche con controlli manuali validi, nessuna attivazione in questa patch.

## File aggiunti

- `trading_bot/core/paper_unlock_manual_switch_preflight.py`
- `trading_bot/run_paper_unlock_manual_switch_preflight.py`
- `trading_bot/test_paper_unlock_manual_switch_preflight.py`
- `docs/patch_reports/PROMPT_29_4_4K_PATCH_REPORT.md`

## File aggiornati

- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`

## Report prodotto

- `data/paper_unlock_manual_switch_preflight_report.json`

## Decisioni possibili

- `MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC`
- `KEEP_DIAGNOSTIC`

`MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC` significa solo che il preflight fail-closed è coerente. Non significa attivazione.

## Safety invariants

Valori hard-blocked dalla patch:

- `operational_unlock_allowed=false`
- `paper_unlock_experiment_allowed=false`
- `paper_orders_enabled=false`
- `profile_activation_allowed=false`
- `automatic_activation_allowed=false`
- `manual_activation_allowed=false`
- `orders_submitted=0`
- `positions_opened=0`

## Test sandbox eseguiti

- `python trading_bot/test_paper_unlock_manual_switch_preflight.py`
- `python trading_bot/test_paper_unlock_experiment_switch_draft.py`
- `python trading_bot/test_paper_unlock_activation_draft.py`
- `python trading_bot/test_paper_unlock_shadow_stability_review.py`
- `python trading_bot/test_paper_unlock_bounded_cadence.py`
- `python trading_bot/test_paper_unlock_shadow_rate_calibration.py`
- `python trading_bot/test_paper_unlock_shadow_dry_run.py`
- `python trading_bot/test_paper_unlock_experiment_design.py`
- `python trading_bot/test_paper_unlock_profile_refinement.py`
- `python trading_bot/test_independent_repaired_validation.py`
- `python trading_bot/test_repaired_structure_shadow_validation.py`
- `python trading_bot/test_structure_context_repair.py`
- `python trading_bot/test_structure_filter_diagnostics.py`
- `python trading_bot/test_calibrated_structure_shadow.py`
- `python trading_bot/test_market_structure_map.py`
- `python trading_bot/test_scenario_pattern_calibration.py`

## Runner sandbox

`python trading_bot/run_paper_unlock_manual_switch_preflight.py` ha prodotto:

- `status=PASS`
- `decision=MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC`
- `switch_draft_ready=true`
- `fail_closed_preflight_ok=true`
- `future_patch_simulation_ok=true`
- `paper_orders_enabled=false`
- `manual_activation_allowed=false`
- `operational_unlock_allowed=false`

## Prossima patch suggerita

`29.4.4l — explicit manual paper-only activation patch draft`, solo se l'utente procede esplicitamente, ancora paper-only/fail-closed e senza live/testnet.
