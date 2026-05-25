# Prompt 29.5.0g — Structure filter diagnostics / confirmation quality audit

## Scopo

Patch diagnostica-only successiva alla 29.5.0f. La 29.5.0f ha mostrato che scenario + pattern + struttura non passano ancora i gate per paper unlock. La 29.5.0g misura *perché* i filtri strutturali non migliorano abbastanza il profilo.

## File aggiunti

- `trading_bot/core/structure_filter_diagnostics.py`
- `trading_bot/run_structure_filter_diagnostics.py`
- `trading_bot/test_structure_filter_diagnostics.py`
- `docs/patch_reports/PROMPT_29_5_0G_PATCH_REPORT.md`

## Output

- `data/structure_filter_diagnostics_report.json`

## Analisi prodotta

Il report misura:

- qualità per `confirmation_summary`;
- qualità per famiglia di conferma: BOS, CHOCH, MSS, demand wait, supply wait, liquidity wait, no structural confirmation;
- qualità per `price_location`;
- allineamento tra `side` e `structure_bias`;
- conflitti direzionali: BUY in supply / SELL in demand;
- contributo di liquidità sopra/sotto;
- bucket di `map_score`;
- failure modes principali;
- varianti audit come `strict_directional_context` e `hard_confirmation_directional`.

## Decisione

La patch non può abilitare trade. Anche se una variante audit risultasse positiva, l'output resta diagnostico e `operational_unlock_allowed=false`.

Decisione attesa nello stato attuale:

```text
KEEP_DIAGNOSTIC
```

## Sicurezza

Invarianti:

```text
no_orders = true
no_live = true
no_testnet = true
risk_unchanged = true
paper_unlock_unchanged = true
operational_unlock_allowed = false
```

## Prossimo step previsto

Se il report conferma conflitti direzionali e bassa qualità delle conferme, la patch successiva consigliata è:

```text
29.5.0h — Strict structure context repair / confirmation relabeling
```

Non procedere a `29.4.4c` finché la struttura non produce varianti con campione, expectancy, win rate e loss rate accettabili.
