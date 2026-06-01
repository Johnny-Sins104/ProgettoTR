# Prompt 29.4.4s-5 — Trade-level telemetry export / Edge forensic foundation

## Stato

Patch preparata in modalità **diagnostic-only**.

Questa patch non abilita live, testnet, exchange broker, paper order routing, order submission, position opening, threshold lowering, forced trades o modifica dei gate esistenti.

## Razionale

La Deep Research ha concluso che ProgettoTR non deve procedere verso nuova esecuzione paper reale finché non esiste una base trade-level verificabile. Gli attuali report aggregati indicano instabilità multi-window e archetype fragili, ma non permettono ancora di ricostruire in modo affidabile:

- sequenza dei trade;
- expectancy in R post-costi;
- distribuzione PnL per archetype/regime/side/sessione;
- cost-to-edge ratio;
- top-trade concentration;
- breakeven drag;
- equity curve e drawdown cronologico;
- MAE/MFE, che resta non disponibile se non viene esportato il percorso barre intra-trade.

## File aggiunti

```text
trading_bot/core/trade_level_telemetry.py
trading_bot/core/equity_forensics.py
trading_bot/run_trade_level_telemetry_export.py
trading_bot/tests/test_trade_level_telemetry.py
trading_bot/tests/test_equity_forensics.py
trading_bot/docs/PROMPT_29_4_4S5_TRADE_LEVEL_TELEMETRY_PATCH_REPORT.md
```

## Output prodotti

Il runner genera:

```text
data/trade_level_telemetry.jsonl
data/trade_level_summary_report.json
data/equity_forensics_report.json
```

## Comando principale

```powershell
python trading_bot\run_trade_level_telemetry_export.py --data-dir data
```

Opzioni utili:

```powershell
python trading_bot\run_trade_level_telemetry_export.py --data-dir data --fee-rate 0.0004 --spread-bps 0 --slippage-bps 0 --starting-equity 1000
```

## Dati ricostruiti

Per ogni `POSITION_CLOSED`, quando disponibile, la patch esporta:

- `position_id`, `order_id`, `cycle_id`;
- `symbol`, `side`;
- `archetype`, `regime`, `scenario`;
- `session_bucket`, `volatility_bucket`;
- `entry_price`, `exit_price`, `qty`, `notional`;
- `stop_loss`, `take_profit`;
- `opened_at`, `closed_at`, `holding_seconds`;
- `exit_reason`;
- `gross_pnl`, `fees_paid`, `net_pnl`;
- `risk_amount`, `r_multiple`;
- `cost_to_edge_ratio`;
- campi `mae_r` e `mfe_r` lasciati a `null` se il bar path intra-trade non è disponibile.

## MAE/MFE

La patch non inventa MAE/MFE da entry/exit-only events.

Quando mancano le barre intra-trade, esporta:

```json
{
  "mae_r": null,
  "mfe_r": null,
  "mae_mfe_status": "UNAVAILABLE_WITHOUT_INTRATRADE_BAR_PATH"
}
```

Questa scelta è intenzionale: per la fase successiva servirà esportare o ricostruire il percorso barre fra apertura e chiusura posizione.

## Report summary

`trade_level_summary_report.json` include breakdown per:

- archetype;
- regime;
- side;
- session bucket;
- volatility bucket.

Include inoltre:

- `closed_trades`;
- `wins`, `losses`, `breakevens`;
- `avg_r`, `median_r`, `min_r`, `max_r`;
- `cost_to_edge_ratio`;
- `top_10_abs_pnl_concentration`;
- `breakeven_drag_detected`;
- `promotion_ready=false`.

## Equity forensics

`equity_forensics_report.json` deriva dai trade chiusi:

- equity curve cronologica;
- final equity;
- net return pct;
- max drawdown;
- max drawdown pct;
- top-trade concentration;
- win/loss streak.

## Decisioni

Decisione positiva del report:

```text
TRADE_LEVEL_TELEMETRY_READY_DIAGNOSTIC
EQUITY_FORENSICS_READY_DIAGNOSTIC
```

Se manca il log eventi:

```text
KEEP_DIAGNOSTIC_NO_EVENT_LOG
```

Se manca la telemetry per equity forensics:

```text
KEEP_DIAGNOSTIC_NO_TRADE_LEVEL_TELEMETRY
```

## Sicurezza

La patch mantiene esplicitamente:

```text
orders_submitted_by_telemetry=0
positions_opened_by_telemetry=0
orders_submitted_by_equity_forensics=0
positions_opened_by_equity_forensics=0
promotion_ready=false
```

Non viene modificato `paper_state.json`. Non viene chiamato `PaperBrokerAdapter.place_order()`. Non viene toccato nessun exchange broker.

## Validazione sandbox

Validazione eseguita:

```text
python -m pytest -q trading_bot/tests/test_trade_level_telemetry.py trading_bot/tests/test_equity_forensics.py
python -m compileall -q trading_bot
python trading_bot/run_trade_level_telemetry_export.py --data-dir data
```

Esito sandbox:

```text
5 passed
compileall OK
runner PASS su dataset sintetico
```

## Prossimo step dopo validazione locale

Dopo installazione locale:

1. eseguire il runner su `data\paper_events.jsonl` reale;
2. ispezionare `trade_level_summary_report.json`;
3. verificare se i trade storici disponibili bastano per breakdown affidabili;
4. se MAE/MFE resta `UNAVAILABLE`, procedere con la patch successiva per esportare bar path intra-trade nei backtest;
5. solo dopo iniziare `29.4.4s-6 — LSR-v2 audit-only candidate detector`.
