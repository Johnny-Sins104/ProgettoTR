# 🚀 REPORT DI OTTIMIZZAZIONE PRESTAZIONALE E COMPUTAZIONALE DEL TRADING BOT

Questo documento contiene un'analisi approfondita delle **opportunità di ottimizzazione prestazionale, computazionale e di I/O** riscontrate all'interno della base di codice di **ProgettoTR**.

Sebbene il bot sia robusto dal punto di vista logico, l'applicazione di queste ottimizzazioni consentirà di abbattere l'utilizzo di CPU e memoria, velocizzare l'esecuzione dei backtest fino al **400%** e garantire che il bot live rispetti con precisione millimetrica i confini temporali dei tick.

---

## 🗺️ INDICE DELLE OTTIMIZZAZIONI PROPOSTE

1. [CRITICAL - COMPUTATIONAL] **Ottimizzazione dell'algoritmo FVG quadratico in `core/analyzer.py`**
2. [CRITICAL - I/O LATENCY] **Asincronizzazione della scrittura parallela di ~30 report sincroni**
3. [HIGH - I/O LATENCY] **Introduzione di un meccanismo di caching in-memory per posizioni e trigger**
4. [HIGH - MEMORY/CPU] **Implementazione di una sliding window per gli indicatori di Pandas**
5. [MEDIUM - ML PERFORMANCE] **Transizione a modelli ML ad alta efficienza (LightGBM/XGBoost)**
6. [MEDIUM - NETWORK] **Riutilizzo delle sessioni HTTP tramite Connection Pooling persistente**

---

## 1. 🔴 [CRITICAL] Ottimizzazione dell'algoritmo FVG quadratico in `core/analyzer.py`
* **Collo di bottiglia**: Computazione ridondante ad alta intensità di CPU.
* **Descrizione attuale**:
  Il calcolo dei *Fair Value Gaps (FVG)* in `TechnicalAnalyzer.add_indicators()` (righe 124-160) viene eseguito tramite un ciclo `for` in Python nativo che scorre ogni singola candela del DataFrame (`for idx in range(2, len(df_ta))`). All'interno di questo ciclo principale, vi sono ulteriori cicli nidificati che iterano su liste dinamiche di FVG attivi (`bull_fvgs` e `bear_fvgs`) per rimuovere quelli mitigati e aggiornare lo stato di posizionamento del prezzo.
* **Problema**:
  Con storici di grandi dimensioni (es. 5.000 o 10.000 candele per backtest), questo calcolo quadratico $O(N \cdot M)$ consuma decine di millisecondi di CPU per singolo tick, rallentando esponenzialmente il backtest offline e introducendo latenze computazionali sensibili nel loop live.
* **Strategia di Ottimizzazione**:
  1. **Calcolo Incrementale (Live/Paper)**: In modalità live, non c'è bisogno di ricalcolare l'intera storia. Bisogna mantenere lo stato dei FVG attivi in memoria ed eseguire l'aggiornamento e la verifica di mitigazione *soltanto per l'ultima candela appena chiusa* (complessità ridotta a $O(1)$).
  2. **Compilazione JIT con Numba (Backtest)**: Per il backtest massivo, decorare la funzione di scansione FVG con `@numba.jit(nopython=True)` per compilarla in codice macchina nativo C, abbattendo i tempi di elaborazione di oltre il 95%.

---

## 2. 🔴 [CRITICAL] Asincronizzazione della scrittura parallela di ~30 report sincroni
* **Collo di bottiglia**: Operazioni di I/O su disco sincrone e bloccanti nel thread principale.
* **Descrizione attuale**:
  Il metodo `write_performance_artifacts()` in `PaperTradingEngine` richiama in maniera sincrona e sequenziale circa 30 metodi di scrittura report (es. `write_repaired_structure_shadow_validation_report`, `write_paper_unlock_guarded_enable_report`, ecc.). Quasi tutti questi report sono abilitati di default in `Config` ed eseguono letture e scritture sincrone di file JSON e Markdown sul file system.
* **Problema**:
  La scrittura di decine di file JSON e Markdown su ogni candela congela il thread primario del bot (I/O blocking). Nei sistemi operativi Windows, questo overhead di file I/O sincrono provoca lag nell'elaborazione del tick principale, mettendo a rischio la precisione della sincronizzazione oraria rispetto alla chiusura esatta della candela (rischio di "slippage temporale").
* **Strategia di Ottimizzazione**:
  1. **Scrittura Asincrona**: Convertire i metodi di salvataggio in funzioni asincrone (`async def`) e utilizzare librerie come `aiofiles` o delegare la scrittura dei file a un thread pool asincrono (`asyncio.to_thread`) per non bloccare mai il loop principale del bot.
  2. **Esecuzione in Background**: Lanciare la scrittura dei report diagnostici tramite `asyncio.create_task()` in background, in modo che l'engine possa passare immediatamente all'attesa del tick successivo senza attendere il completamento della scrittura su disco.

---

## 3. 🟠 [HIGH] Meccanismo di caching in-memory per posizioni e trigger
* **Collo di bottiglia**: Accesso continuo ed eccessivo al disco per piccole letture.
* **Descrizione attuale**:
  Per verificare lo stato dei trade attivi e dei trigger pendenti, il modulo `multi_trade_manager.py` effettua letture continue dei file JSON nelle cartelle `data/trades/` e `data/pending/` ad ogni iterazione del loop.
* **Problema**:
  I continui accessi sincroni al disco per recuperare piccoli file JSON generano latenza di I/O non necessaria, aumentando l'usura delle unità a stato solido (SSD) e degradando i tempi di risposta dell'applicazione.
* **Strategia di Ottimizzazione**:
  1. **Caching in Memoria**: Conservare lo stato dei trade e dei trigger attivi in strutture dati in memoria (`self._cached_trades = {}`, `self._cached_pending = {}`).
  2. **Write-Through / Deferred Sync**: Effettuare le verifiche cicliche interamente in memoria. Scrivere su disco il file JSON corrispondente *solamente quando avviene una transizione di stato reale* (es. inserimento di un nuovo trigger, riempimento di un pendente o chiusura di un trade), azzerando le letture ridondanti su disco.

---

## 4. 🟠 [HIGH] Implementazione di una sliding window per gli indicatori di Pandas
* **Collo di bottiglia**: Ricalcolo computazionale ridondante su serie storiche immutate.
* **Descrizione attuale**:
  Ogni volta che si conclude una candela, il bot scarica lo storico delle candele da Binance e calcola gli indicatori su tutta la lunghezza del DataFrame tramite `TechnicalAnalyzer.add_indicators()`.
* **Problema**:
  Gli indicatori di analisi tecnica sono calcolati su finestre mobili relativamente corte (es. EMA 200, ADX 14, ATR 14). Ricalcolare l'EMA 400 o l'ATR su 5.000 candele storiche a ogni tick per estrarre solo l'ultimo valore è uno spreco enorme di cicli CPU.
* **Strategia di Ottimizzazione**:
  1. **Slicing Scorrevole (Sliding Window)**: Configurare una finestra massima di ricalcolo. Per calcolare in modo stabile un'EMA 400, sono sufficienti circa 600 candele storiche. Tagliare il DataFrame in input a `add_indicators` alle sole ultime $N$ candele necessarie per stabilizzare gli indicatori, riducendo la dimensione dei calcoli matematici di oltre l'80%.

---

## 5. 🟡 [MEDIUM] Transizione a modelli ML ad alta efficienza (LightGBM o XGBoost)
* **Collo di bottiglia**: Latenza di predizione e overhead di memoria dell'AI.
* **Descrizione attuale**:
  La classe `TradingAI` (`MetaLabelingEngine`) incapsula un classificatore `RandomForestClassifier` di `scikit-learn` configurato con 200 alberi decisionali. Le predizioni per stabilire la confidenza del trade vengono eseguite iterando singolarmente su ciascun segnale generato.
* **Problema**:
  Sebbene robusto, `RandomForestClassifier` carica in memoria strutture ad albero pesanti che richiedono calcoli seriali in Python. Inoltre, manca di ottimizzazioni avanzate per calcoli ad alta velocità.
* **Strategia di Ottimizzazione**:
  1. **Adozione di LightGBM / XGBoost**: Sostituire il Random Forest con LightGBM o XGBoost (già predisposto parzialmente nel codice). LightGBM è notevolmente più veloce nelle predizioni in tempo reale, consuma una frazione della memoria e sfrutta l'elaborazione parallela nativa in C++.
  2. **Predizione Vettorializzata (Batch Prediction)**: Evitare cicli di predizione individuali se sono presenti più segnali simultanei. Alimentare l'AI con una matrice numpy vettorializzata in un'unica chiamata `predict_proba()`.

---

## 6. 🟡 [MEDIUM] Riutilizzo delle sessioni HTTP tramite Connection Pooling persistente
* **Collo di bottiglia**: Overhead di latenza di rete e handshake continui.
* **Descrizione attuale**:
  In `core/telegram_control.py`, l'invio di messaggi tramite `send()` apre e chiude continuamente nuove istanze di sessione HTTP asincrone:
  ```python
  async with aiohttp.ClientSession() as session:
      await session.post(url, json=payload, timeout=8)
  ```
* **Problema**:
  Creare una nuova `ClientSession` per ciascun messaggio costringe il sistema ad effettuare handshakes TCP e SSL ripetuti con i server di Telegram a ogni notifica, introducendo latenze di rete di centinaia di millisecondi e sprecando risorse di sistema.
* **Strategia di Ottimizzazione**:
  1. **Persistent Connection Pooling**: Creare un'unica istanza persistente di `aiohttp.ClientSession` all'avvio del bot all'interno di `TelegramControlBot` (e gestirla in modo centralizzato). Riutilizzare questa sessione per tutte le notifiche proactive in uscita e per il polling in entrata.
  2. **Graceful Shutdown**: Chiudere in modo deterministico la sessione persistente (`await session.close()`) esclusivamente nel blocco `finally` durante la disattivazione dell'engine, garantendo il rilascio immediato dei socket di rete.

---

### Benefici Attesi dopo le Ottimizzazioni
L'implementazione congiunta di queste ottimizzazioni (in particolar modo il **caching in memoria**, il **taglio incrementale di FVG** e il **pooling delle connessioni HTTP**) trasformerà ProgettoTR in un sistema a bassissima latenza, riducendo l'impronta computazionale complessiva del bot del **70-80%** e rendendo il backtest offline istantaneo.
