# Skill: execution-cost-validation

## Scopo

Cost model diagnostico, economicamente corretto e riutilizzabile da benchmark, backtest e walk-forward. Calcola gross PnL, costi per componente e net PnL/R senza conversione diretta bps→R.

## Modulo principale

`trading_bot/core/unified_trade_cost.py`

## Formula critica

```
gross_pnl     = (exit - entry) * qty * direction   # direction = +1 BUY, -1 SELL
notional      = entry * qty
exit_notional = exit * qty
fee_entry_amt = notional * fee_entry_bps / 10000
fee_exit_amt  = exit_notional * fee_exit_bps / 10000   # usa exit_notional
spread_amt    = notional * spread_bps / 10000
slippage_amt  = notional * slippage_bps / 10000
latency_amt   = notional * latency_bps / 10000
partial_fill_amt = notional * partial_fill_bps / 10000
total_cost    = somma di tutti e 6 i componenti
net_pnl       = gross_pnl - total_cost
initial_risk  = abs(entry - stop) * qty
gross_R       = gross_pnl / initial_risk
net_R         = net_pnl / initial_risk
cost_R        = total_cost / initial_risk
```

**VINCOLO:** Non convertire mai bps → R direttamente. Il rapporto notional/initial_risk è il fattore di leva che determina il valore reale di cost_R.

## Parità API (Prompt 3A — OBBLIGATORIO)

`compute_trade_outcome()` e `apply_cost_to_backtest_trade()` usano **la stessa funzione interna**
`_compute_cost_amounts(entry_notional, exit_notional, bps)`. La parità è **ESATTA** su tutti i trade
— flat e non-flat. Non esiste alcuna "approssimazione documentata".

`apply_cost_to_backtest_trade` richiede `entry_price, exit_price, quantity` esplicitamente.
Se il chiamante non ha il prezzo di uscita disponibile, deve sollevare un errore — non stimare silenziosamente.

## Scenari (4)

| Scenario | Entry | Exit | Bps RT BTC/15m | Fill Prob |
|---------|-------|------|----------------|-----------|
| optimistic | LIMIT | LIMIT | ~5.0 | 0.98 |
| realistic | MARKET | MARKET | ~10.0 | 0.96 |
| conservative | MARKET + stress×1.75 | MARKET | ~13.25 | 0.93 |
| severe | MARKET + stress×2.75 | MARKET | ~25.875 | 0.85 |

## Bps per simbolo e timeframe (realistic, atr=0)

| Simbolo | 15m | 5m |
|---------|-----|----|
| BTC/USDT | 10.0 | 10.4 |
| ETH/USDT | 10.0 | 10.4 |
| XRP/USDT | 10.4 | 10.88 |
| SOL/USDT | 10.0 | 10.4 |
| BNB/USDT | 10.0 | 10.4 |

## API

```python
from core.unified_trade_cost import UnifiedCostModel, SCENARIO_NAMES

# Singolo trade, scenario scelto
outcome = UnifiedCostModel.compute_trade_outcome(
    side="BUY",
    entry_price=50000, exit_price=51000, stop_price=49500,
    quantity=0.01, scenario="realistic",
    symbol="BTC/USDT", timeframe="15m", atr_pct=0.5
)
print(outcome.gross_R, outcome.net_R, outcome.total_cost_amt)

# Tutti gli scenari
outcomes = UnifiedCostModel.all_scenarios(
    side="BUY", entry_price=50000, exit_price=51000,
    stop_price=49500, quantity=0.01, symbol="BTC/USDT", timeframe="15m"
)

# Applicare al backtest (gross_pnl noto, entry_price/exit_price/quantity richiesti)
result = UnifiedCostModel.apply_cost_to_backtest_trade(
    gross_pnl=10.0, initial_risk=5.0,
    entry_price=50000.0, exit_price=51000.0, quantity=0.01,
    scenario="conservative", symbol="BTC/USDT", timeframe="5m"
)
print(result["net_R"], result["cost_R"])

# Solo bps breakdown
bps = UnifiedCostModel.bps_for_scenario("severe", "XRP/USDT", "5m", atr_pct=1.0)
print(bps["total_round_trip_bps"])
```

## Comandi

```bash
# Runner validazione
python trading_bot/run_cost_model_validation.py

# Test unitari con casi numerici verificabili
python -m pytest trading_bot/tests/test_unified_trade_cost.py -v

# Output
cat data/cost_model_validation.json | python -m json.tool | head -40
```

## Regole fail-closed (Prompt 3A — aggiornate)

Tutti i metodi pubblici sollevano `ValueError` su input non validi. Nessun default silenzioso.

| Input non valido | Metodo | Eccezione |
|-----------------|--------|-----------|
| `side` non BUY/SELL | `compute_trade_outcome` | ValueError |
| `scenario` non in SCENARIO_NAMES | tutti i metodi pubblici | ValueError |
| `entry_price ≤ 0` | `compute_trade_outcome` | ValueError |
| `exit_price ≤ 0` | `compute_trade_outcome` | ValueError |
| `stop_price ≤ 0` | `compute_trade_outcome` | ValueError |
| `quantity ≤ 0` | `compute_trade_outcome` | ValueError |
| `stop_price == entry_price` | `compute_trade_outcome` | ValueError |
| **BUY con stop >= entry** | `compute_trade_outcome` | ValueError (Prompt 3A) |
| **SELL con stop <= entry** | `compute_trade_outcome` | ValueError (Prompt 3A) |
| **NaN in qualsiasi float** | tutti i metodi pubblici | ValueError (Prompt 3A) |
| **+Inf/-Inf in qualsiasi float** | tutti i metodi pubblici | ValueError (Prompt 3A) |
| **timeframe non supportato** | tutti i metodi pubblici | ValueError (Prompt 3A — nessun fallback a 15m) |
| `entry_price ≤ 0` | `apply_cost_to_backtest_trade` | ValueError |
| `exit_price ≤ 0` | `apply_cost_to_backtest_trade` | ValueError |
| `quantity ≤ 0` | `apply_cost_to_backtest_trade` | ValueError |
| `initial_risk ≤ 0` | `apply_cost_to_backtest_trade` | ValueError |

**Timeframe supportati:** `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"` — qualsiasi altro valore solleva ValueError.

Scenari validi: `"optimistic"`, `"realistic"`, `"conservative"`, `"severe"`.
Bannati da benchmark: `"LOW"`, `"MEDIUM"`, `"HIGH"`, `"DYNAMIC"`, `"Kelly"` — tutti sollevano ValueError.

## Componenti cost (tutti e 6 in total_cost_amt)

```
total_cost_amt = fee_entry_amt + fee_exit_amt + spread_amt
               + slippage_amt + latency_amt + partial_fill_amt
```

`fee_exit_amt` usa `exit_notional = exit_price * quantity` (esatto, non approssimato).
`fee_entry_amt`, `spread_amt`, `slippage_amt`, `latency_amt`, `partial_fill_amt` usano `entry_notional`.

## Risk policy per Fasi 3-5 (Prompt 3A — OBBLIGATORIO)

```
risk_per_trade_pct = 0.005   # 0.5% di equity per trade — NON 0.5 (che sarebbe 50%)
```

Il valore numerico è `0.005`. Label: "0.5%". `risk_budget = equity * 0.005`.

Profili di sizing **bannati** dal benchmark:
- `LOW`, `MEDIUM`, `HIGH` — non definiti / non calibrati
- `DYNAMIC` — riservato ad ablazione post-OOS, solo reduce-only, non live
- `Kelly` — escluso

## Integrazione con backtest (Prompt 3A)

```python
# Nel loop backtest, per ogni trade chiuso — RICHIEDE entry_price, exit_price, quantity
result = UnifiedCostModel.apply_cost_to_backtest_trade(
    gross_pnl=trade.gross_pnl,
    initial_risk=trade.initial_risk,
    entry_price=trade.entry_price,    # OBBLIGATORIO (non "notional")
    exit_price=trade.exit_price,      # OBBLIGATORIO (non "notional")
    quantity=trade.quantity,          # OBBLIGATORIO
    scenario=cost_scenario,           # "realistic" per default
    symbol=asset,
    timeframe=tf,
)
backtest_results.append({
    "gross_R": result["gross_R"],
    "net_R": result["net_R"],
    "cost_R": result["cost_R"],
})
```
