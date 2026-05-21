# Agentic AI Trading Bot con Machine Learning e Context-Awareness

Questo documento fornisce una descrizione tecnica, architetturale e funzionale completa del trading bot evoluto sviluppato finora. Il sistema è progettato per operare su **Binance Futures USDT-M** (timeframe di riferimento 15m) ed evolve una classica strategia a regole fisse in un **ecosistema probabilistico guidato dall'intelligenza artificiale**.

---

## 1. Architettura di Sistema

Il bot è strutturato secondo principi di alta modularità, separazione delle responsabilità e robustezza all'esecuzione sincrona e asincrona. La struttura dei file principale è la seguente:

```
trading_bot/
├── config.py                 # Configurazione centralizzata e parametri evoluti
├── main.py                   # Loop asincrono principale per l'operatività Live
├── backtest_lab.py           # Simulatore storico multi-profilo integrato con AI
├── multi_trade_manager.py    # Gestore asincrono multi-trade e posizioni pendenti
├── run_custom_backtest.py    # CLI per l'avvio rapido di simulazioni storiche
├── requirements.txt          # Dipendenze del progetto (compreso scikit-learn)
├── core/
│   ├── __init__.py
│   ├── client.py             # Client CCXT asincrono per Binance Futures
│   ├── analyzer.py           # Estrazione di oltre 25 indicatori tecnici
│   ├── engine.py             # Decision Engine pesato con Regime Switching e AI Hybrid
│   ├── risk.py               # RiskManager e calcolo position sizing (Kelly Criterion)
│   ├── data_collector.py     # Modulo Memoria: estrazione features e labeling forward
│   └── ai_engine.py          # Cervello Predittivo: Random Forest Classifier
└── data/                     # File di log, database SQLite, file JSON dei trade
```

---

## 2. Moduli Funzionali e Flussi Dati

### 📊 A. Analizzatore Tecnico (`core/analyzer.py`)
L'analizzatore converte i dati grezzi (OHLCV) scaricati dall'exchange o caricati da file cache in un set ricco di indicatori tecnici, tra cui:
*   **Trend a lungo termine**: EMA a 200 e 400 periodi.
*   **Momentum**: RSI a 14 periodi.
*   **Volatilità e Trend Strength**: ADX e ATR (Average True Range).
*   **Strutture dei Volumi**: Calcolo del *Volume Bias* (Bullish/Bearish/Neutral) basato sul delta volumetrico cumulato delle ultime 5 candele.
*   **Price Action & Struttura del Mercato**:
    *   *Supporti e Resistenze locali*: Calcolo di massimi e minimi di swing recenti.
    *   *Livelli Psicologici*: Calcolo della vicinanza a multipli chiave del prezzo (es. multipli di 250 USDT per BTC).
    *   *Fair Value Gaps (FVG)*: Identificazione di inefficienze di prezzo (Bullish e Bearish).
    *   *Macro-Range Position*: Rilevamento della posizione percentuale del prezzo all'interno del canale a 400 candele (`range_pos_400`).
    *   *Pattern di Candele*: Rilevamento automatico di candele *Doji* ed *Engulfing* (Bullish/Bearish).
*   **Regime Switching**: Classificazione automatica del mercato in `TRENDING` o `RANGING` basata sull'ADX rispetto alla soglia ottimale.

---

### 📝 B. Modulo Memoria (`core/data_collector.py`)
Questo modulo è l'infrastruttura di persistenza delle features che rende possibile l'apprendimento continuo. Per ogni candela (o per ogni segnale), il modulo estrae **15 features strutturate** e le associa a una **label di outcome**:

#### Features Estratte:
1.  `rsi`: RSI 14 diretto.
2.  `adx`: ADX diretto.
3.  `atr_pct`: ATR normalizzato come percentuale del prezzo close (`ATR / Close * 100`).
4.  `ema_slope`: Pendenza percentuale dell'EMA 200 negli ultimi 5 periodi.
5.  `close_vs_ema`: Distanza percentuale tra il prezzo di chiusura e l'EMA 200.
6.  `dist_to_psy`: Distanza percentuale dal livello psicologico più vicino.
7.  `volume_ratio`: Rapporto tra il volume attuale e la media rolling a 20 periodi.
8.  `bb_position`: Posizione percentuale nel macro-canale (`bb_position` o `range_pos_400`).
9.  `engulfing`: Pattern engulfing codificato come `-1.0` (Bearish), `0.0` (Nessuno) o `1.0` (Bullish).
10. `regime`: Stato di mercato (`1` per Trending, `0` per Ranging).
11. `in_fvg`: Presenza all'interno di un Fair Value Gap (`1` Bullish, `-1` Bearish, `0` Nessuno).
12. `near_sr`: Vicinanza a livelli S/R chiave (`1` vicino al supporto, `-1` vicino alla resistenza, `0` Nessuno).
13. `hour`: Ora del giorno (componente ciclica).
14. `day_of_week`: Giorno della settimana (0-6).
15. `volume_bias_enc`: Direzione dei volumi (`1` Bullish, `-1` Bearish, `0` Neutral).

#### Simmetria dello Short:
Per evitare che l'algoritmo debba apprendere separatamente a comprare e vendere raddoppiando la quantità di dati necessari, il bot implementa la **Symmetry Transformation** per i segnali Short (SELL). Prima di salvare o predire su un segnale Short, le features direzionali (`engulfing`, `close_vs_ema`, `ema_slope`, `near_sr`, `volume_bias_enc`) vengono **invertite di segno**. In questo modo, l'AI impara la forma geometrica del setup di inversione indipendentemente dalla direzione fisica del grafico.

#### Labeling Forward (`label_outcome`):
La label `outcome` viene calcolata simulando proattivamente l'evoluzione storica del prezzo per le successive **100 candele**:
*   Ritorna `1` (Win) se il prezzo raggiunge il **Take Profit** (calcolato con l'ATR e il Reward-Risk specificato) prima di toccare lo **Stop Loss**.
*   Ritorna `0` (Loss) se colpisce prima lo **Stop Loss** o in caso di timeout (superamento di 100 candele).

---

### 🧠 C. Cervello Predittivo (`core/ai_engine.py`)
La classe `TradingAI` incapsula il modello di Machine Learning:
*   **Modello**: Utilizza la libreria `scikit-learn` implementando un **Random Forest Classifier** (`n_estimators=200`, `max_depth=10`, `min_samples_leaf=4`) ottimizzato per mitigare l'overfitting.
*   **Split Temporale**: Il dataset viene diviso in 80% training e 20% test con shuffle.
*   **Fallback di Sicurezza**: Se la libreria non è installata o il file `market_features.csv` non ha raggiunto il numero minimo di campioni (`AI_MIN_SAMPLES = 200`), l'AI restituisce automaticamente una probabilità del `50.0%` (neutra), disattivando silenziosamente il modulo e lasciando l'operatività al 100% sul motore tecnico tradizionale (Zeroloss/Zero-downtime).
*   **Apprendimento Continuo (Auto-Retrain)**: Il modello viene monitorato in tempo reale e si riaddestra automaticamente in background ogni 500 nuovi campioni accumulati (`retrain_if_needed`).

---

### ⚖️ D. Motore Decisionale Ibrido (`core/engine.py` - `DecisionEngine`)
Combina l'analisi tecnica classica con l'intelligenza predittiva:
1.  **Punteggio Tecnico Pesato**: Calcola lo score tecnico pesato basato sul regime di mercato corrente.
2.  **Fattore AI**: Se la modalità è impostata su `AI_HYBRID`, estrae le features correnti e interroga l'AI.
3.  **Punteggio Combinato (Score Ibrido)**:
    $$\text{Hybrid Score} = (\text{Tech Score} \times 0.6) + (\text{AI Score} \times 0.4)$$
    dove lo `Tech Score` va da -100 a +100 e l'`AI Score` viene mappato linearmente dalla probabilità (0-100%) in un range simmetrico -100 e +100.
4.  **Filtro Anti-Fakeout**: Se il segnale tecnico è positivo (BUY/SELL) ma l'AI calcola una probabilità di successo **inferiore al 55%** (`AI_MIN_CONFIDENCE`), il verdetto viene forzato a `"HOLD"`, prevenendo ingressi rischiosi in zone di indecisione del mercato.

---

### 💰 E. Gestore del Rischio Avanzato (`core/risk.py` - `RiskManager`)
Implementa il **Kelly Criterion** per ottimizzare matematicamente la crescita del capitale riducendo i drawdown sistematici:
*   **Formula di Kelly**:
    $$f^* = \frac{p \cdot b - q}{b}$$
    dove:
    *   $p$: Probabilità statistica di vincita predetta dall'AI (espressa come decimale, es. 0.65).
    *   $b$: Rapporto Reward/Risk del trade corrente (es. 2.0).
    *   $q$: Probabilità di perdita ($1 - p$).
*   **Frazionamento (Half-Kelly)**: Per proteggere il conto da oscillazioni di varianza statistica del mercato e stime ottimistiche, il bot applica un moltiplicatore frazionario del 50% (`KELLY_FRACTION = 0.5`).
*   **Safety Capping & Floor**: Il rischio calcolato tramite Kelly viene rigidamente limitato per motivi di sicurezza:
    *   *Minimo*: `1.5%` del capitale (per garantire operatività).
    *   *Massimo*: Limitato alla percentuale originale della classe di rischio impostata (es. `15.0%` del conto per il profilo HIGH) per evitare sovraesposizioni estreme.

---

### 📈 F. Gestore Asincrono Posizioni (`multi_trade_manager.py`)
Mentre i vecchi bot bloccavano il flusso restando in attesa della chiusura di un trade (monitorando 1 operazione alla volta), il `multi_trade_manager` gestisce il portafoglio in modo asincrono e non-bloccante:
*   Supporta fino a **`MAX_CONCURRENT_TRADES`** posizioni attive simultaneamente.
*   **Gestione Ordini Pendenti (Breakout Trigger)**: All'attivazione di un segnale, il bot non entra direttamente a mercato se non è verificato il breakout, ma crea un trigger pendente in `data/pending/` con un tempo di vita (TTL) massimo di 2 candele. Se il prezzo rompe il massimo (BUY) o il minimo (SELL) della candela di segnale entro il TTL, il trade viene aperto, calcolandone la taglia dinamica in base alle formule di Kelly.
*   **Monitoraggio Ciclico**: Ad ogni ciclo (e candela), scansiona tutti i file json in `data/trades/` confrontando il prezzo di Binance con i livelli di TP e SL, chiudendo le posizioni all'istante al tocco dei target.
*   **Registrazione Outcome**: All'atto della chiusura del trade, le features originarie vengono recuperate e salvate in `market_features.csv` con l'outcome reale (`1` se chiuso in TP, `0` se chiuso in SL), alimentando direttamente l'apprendimento continuo live.

---

## 3. Loop Operativo Live (`main.py`)

Il file `main.py` orchestra il funzionamento live su Binance Futures:
1.  **Sincronizzazione Temporale**: All'avvio, il loop asincrono calcola i secondi mancanti alla chiusura della candela da 15 minuti ed entra in uno stato di attesa attiva (`sleep`), garantendo l'esecuzione del codice esattamente a candela chiusa.
2.  **Verifica Target Giornaliero**: All'inizio di ogni iterazione, controlla se il saldo corrente ha raggiunto l'obiettivo impostato in `PROFIT_TARGET_PCT` (es. +60% del capitale iniziale). Se raggiunto, invia una notifica di successo su Telegram e spegne in sicurezza il bot per proteggere i profitti.
3.  **Controlli Ciclici**:
    *   Aggiorna e monitora i trade attivi.
    *   Aggiorna e monitora la scadenza o l'attivazione dei trigger pendenti.
4.  **Generazione Segnale**:
    *   Scarica gli storici OHLCV recenti da Binance.
    *   Analizza il DataFrame tramite `TechnicalAnalyzer`.
    *   Se non ci sono posizioni piene, interroga il `DecisionEngine`.
    *   In caso di segnale BUY o SELL valido (superato anche il filtro anti-fakeout dell'AI), estrae le features live, stima la confidenza dell'AI e salva un trigger pendente.

---

## 4. Piattaforma di Simulazione e Test (`backtest_lab.py`)

Funge da laboratorio di prova offline e validazione scientifica:
1.  **Caricamento Dati offline**: Utilizza cache locali (es. `data/btc_15m_cache.csv`) per consentire backtest rapidi su migliaia di candele senza pesare sui limiti di API dell'exchange.
2.  **Addestramento pre-simulazione**: Genera in modo massivo le features e la label reale per l'intero DataFrame storico, addestrando l'AI prima di avviare il loop.
3.  **Simulazione Multi-Rischio Comparativa**: Esegue la simulazione contemporaneamente su 4 profili di rischio distinti per consentire all'utente un confronto immediato:
    *   *Low Risk*: 3% di rischio massimo per trade, leva massima 4x.
    *   *Medium Risk*: 7% di rischio massimo per trade, leva massima 8x.
    *   *High Risk*: 15% di rischio massimo per trade, leva massima 10x.
    *   *Dynamic Kelly Risk*: Position sizing dinamico regolato dal Kelly Criterion basato sulla reale probabilità dell'AI.
4.  **Generazione Grafici**: Se configurato, salva in `data/charts/` dei grafici interattivi in formato HTML per ciascun trade chiuso, mostrando con precisione i punti di ingresso, stop loss, take profit ed evoluzione del prezzo.
5.  **Output di Performance**: Espone una tabella di riepilogo con Saldo Finale, Net PnL %, Max Drawdown %, Win Rate globale ed una vista dettagliata delle metriche di accuratezza dell'AI e le feature più rilevanti.

---

## 5. Ecosistema Avanzato (Portfolio, Execution, Regime)

Il sistema include moduli istituzionali avanzati introdotti di recente:
*   **Regime-Specialized ML**: Anziché un modello unico, il bot può usare modelli separati per mercati Trending vs Ranging e per Alta vs Bassa volatilità (`run_regime_comparison.py`), migliorando l'adattabilità.
*   **Multi-Asset Portfolio Engine**: Estensione per operare simultaneamente su BTC, ETH, SOL, XRP e BNB (`run_portfolio_backtest.py`), con controllo della correlazione rolling e limiti di esposizione settoriale (Portfolio VaR).
*   **Execution Friction Simulation**: Simulatore istituzionale (`run_execution_analysis.py`) basato sull'Implementation Shortfall (Perold 1988) per misurare l'impatto reale di slippage, spread dinamico e liquidity-aware partial fills, rivelando il degrado statistico dei backtest "ideali".

---

## 6. Guida ai Backtest e Simulazioni

Per eseguire i test, il progetto dispone di vari entry-point a seconda del livello di profondità richiesto:

1.  **Backtest Rapido Interattivo** (`avvia_backtest.bat` in cartella root): Batch script interattivo per test veloci (chiede capitale iniziale e candele a schermo).
2.  **Laboratorio Core dell'AI** (`trading_bot/backtest_lab.py`): Esegue la walk-forward validation completa, meta-labeling, e mostra il confronto simultaneo tra 4 profili di rischio (Low, Medium, High, Kelly).
3.  **Backtest di Portafoglio Multi-Asset** (`trading_bot/run_portfolio_backtest.py`): Simula il trading simultaneo su 5 asset calcolando la correlazione.
4.  **Confronto Modelli Specializzati vs Unificati** (`trading_bot/run_regime_comparison.py`): Backtesta i modelli ad-hoc per regime rispetto alla baseline.
5.  **Analisi Execution Friction** (`trading_bot/run_execution_analysis.py`): Esegue diagnostiche per confrontare i profitti di un backtest ingenuo con quelli filtrati dalla frizione reale di esecuzione.

---

Questo sistema rappresenta lo stato dell'arte nello sviluppo di trading bot quantitativi, unendo la rigidità protettiva dell'analisi tecnica, l'intelligenza probabilistica del meta-labeling Machine Learning, e un sofisticato controllo del rischio di portafoglio e di mercato.
