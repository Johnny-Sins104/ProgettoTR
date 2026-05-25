# Prompt 29.5.0i — Repaired structure shadow validation / MAP_SCORE_65_79 and BOS component audit

## Scope

Patch diagnostica-only successiva alla 29.5.0h. Valida le righe `scenario + pattern + structure` dopo il repair semantico `CONTEXT / WAIT / CONFIRMATION / CONFLICT / NO_STRUCTURE`.

Focus della patch:

- validazione del sottoinsieme `MAP_SCORE_65_79` dopo repair;
- audit del componente BOS direzionale;
- audit di CHOCH/MSS direzionali come controllo secondario;
- separazione esplicita di `WAIT` e `NO_STRUCTURE` come watchlist-only / non-entry;
- breakdown per asset, side, state, confirmation_summary e price_location;
- report JSON: `data/repaired_structure_shadow_validation_report.json`.

## Safety invariants

La patch non abilita operatività.

- `opens_orders = false`
- `enables_live_or_testnet = false`
- `changes_thresholds = false`
- `operational_unlock_allowed = false`
- `paper_unlock_refinement_allowed = false`
- nessun cambio rischio
- nessun paper unlock
- nessun testnet
- nessun live reale

## Files

Nuovi file:

- `trading_bot/core/repaired_structure_shadow_validation.py`
- `trading_bot/run_repaired_structure_shadow_validation.py`
- `trading_bot/test_repaired_structure_shadow_validation.py`
- `docs/patch_reports/PROMPT_29_5_0I_PATCH_REPORT.md`

File integrati:

- `trading_bot/config.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/run_paper_trading.py`

## Validation variants

La patch genera varianti diagnostiche tra cui:

- `entry_state_context_or_confirmation`
- `repaired_confirmation_only`
- `clean_pattern_range_repaired_entry_state`
- `map_score_65_79_all`
- `map_score_65_79_repaired_entry_state`
- `map_score_65_79_repaired_confirmation`
- `map_score_65_79_clean_repaired_entry_state`
- `bos_directional_repaired`
- `bos_directional_clean_repaired`
- `choch_directional_repaired`
- `mss_directional_repaired`
- `wait_states_watchlist_only`
- `no_structure_anomaly_watchlist_only`
- `btc_focus_clean_repaired_entry_state`
- `btc_focus_clean_repaired_confirmation`
- `btc_focus_map_score_65_79_clean_repaired_entry`
- `btc_focus_bos_clean_repaired`

`WAIT`, `NO_STRUCTURE` e `CONFLICT` non possono diventare entry candidate anche se mostrano expectancy positiva nel campione.

## Gate diagnostici

Default:

- `min_candidates >= 50`
- `expectancy_r >= +0.10`
- `win_rate_pct >= 52.0`
- `loss_rate_pct <= 45.0`
- `time_exit_rate_pct <= 60.0`

Anche se una variante passasse i gate, la decisione sarebbe solo `VALIDATION_CANDIDATE_DIAGNOSTIC` e `operational_unlock_allowed` resterebbe `false`.

## Local validation commands

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\test_repaired_structure_shadow_validation.py
python trading_bot\run_repaired_structure_shadow_validation.py
type data\repaired_structure_shadow_validation_report.json
```

## Expected decision

Esito conservativo atteso:

```text
status = WARN
decision = KEEP_DIAGNOSTIC
operational_unlock_allowed = false
orders_submitted = 0
positions_opened = 0
```

Se dovesse uscire `VALIDATION_CANDIDATE_DIAGNOSTIC`, non significa sblocco operativo; significa solo che una variante deve essere validata da una patch successiva con stabilità/walk-forward indipendente.
