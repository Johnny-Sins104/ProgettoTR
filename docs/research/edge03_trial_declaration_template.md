# Edge Research 03 — Dichiarazione ex-ante dei trial

> Compilare PRIMA di qualunque run di validazione. Dopo la registrazione con
> `declare_trials()` (max 12 config per famiglia, numerazione cumulativa da 84)
> nessuna config può essere aggiunta, rimossa o modificata. Le run su config
> non dichiarate falliscono (fail-closed).

## Famiglia: TSMOM (trend-following 4h/1d)

**Ipotesi economica** (perché questo edge dovrebbe esistere ai costi taker ~10 bps RT):

> _es.: la persistenza dei trend multi-settimana sulle large cap cripto è documentata;
> su 4h/1d il costo per trade è diluito 10-50x per unità di movimento atteso rispetto
> all'intraday, che i cicli 1-2 hanno dimostrato non sopravvivere ai costi._

**Criteri di kill** (cosa chiude la famiglia senza appello):

> _es.: PF pooled < 1.0 sul train; nessun plateau di parametri (vicini che passano);
> pnl positivo solo in regime bull._

**Griglia dichiarata** (max 12, ogni riga una `TSMOMConfig`):

| # | lookback_bars | vol_target_ann | timeframe | long_short | Motivazione economica |
|---|---------------|----------------|-----------|------------|----------------------|
| 1 |               |                |           |            |                      |
| 2 |               |                |           |            |                      |
| … |               |                |           |            |                      |

## Famiglia: Funding Carry (perpetual)

**Ipotesi economica**:

> _es.: il funding positivo persistente è un premio strutturale pagato dai long
> levereggiati; lo short che lo incassa non richiede previsione del prezzo, solo
> che il drift avverso non superi il carry. Riportare i risultati CON e SENZA
> funding per esporre la dipendenza dal carry._

**Criteri di kill**:

> _es.: pnl con funding ≤ pnl senza funding (il carry non paga); drawdown da
> squeeze > 15%; segnale concentrato in un solo mese._

**Griglia dichiarata** (max 12, ogni riga una `CarryConfig`):

| # | metric | window_events | entry_threshold | exit_threshold | max_hold_bars | timeframe | Motivazione |
|---|--------|---------------|-----------------|----------------|---------------|-----------|-------------|
| 1 |        |               |                 |                |               |           |             |
| 2 |        |               |                 |                |               |           |             |
| … |        |               |                 |                |               |           |             |

## Registrazione

```python
from trading_bot.research.edge03.declared_trials import declare_trials
from trading_bot.research.edge03.families import TSMOMConfig, CarryConfig

tsmom_grid = (
    TSMOMConfig(lookback_bars=..., vol_target_ann=..., timeframe=..., long_short=...),
    # ... max 12
)
carry_grid = (
    CarryConfig(metric=..., window_events=..., entry_threshold=...,
                exit_threshold=..., max_hold_bars=..., timeframe=...),
    # ... max 12
)

print(declare_trials("tsmom", tsmom_grid))          # → [85, ...]
print(declare_trials("funding_carry", carry_grid))  # → [..., ≤108]
```

Il log cumulativo viene emesso in `data/research/edge03_trial_log.json`.
Committare il log insieme a questo file compilato PRIMA della prima run.
