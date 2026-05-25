# 🔍 REPORT COMPLETO DI AUDIT E ANALISI DEI PROBLEMI DEL TRADING BOT

Questo documento contiene un'analisi dettagliata dei problemi, bug latenti, colli di bottiglia e difetti di design architetturale riscontrati all'interno della base di codice del bot di trading quantitativo **ProgettoTR** (Prompt 29 e successivi).

L'audit ha rivelato **13 problemi chiave** classificati in base alla gravità, con spiegazioni del loro impatto e raccomandazioni precise per risolverli.

---

## 🗺️ INDICE DEI PROBLEMI RILEVATI

1. [CRITICAL - PORTABILITY] **Crash da codifica caratteri non-ASCII su terminali Windows (CP1252 / Locale Italiano)**
2. [CRITICAL - RISK] **Stato di VaR obsoleto (off-by-one) nel calcolo dei Flag di Concentrazione del Portafoglio**
3. [HIGH - CONCURRENCY] **Blocco del processo di chiusura asincrono in modalità `--once` (Hang di `aiohttp`)**
4. [HIGH - ML LOGIC] **Glitch logico nel meccanismo di auto-addestramento dell'AI (Modulo permanente saltato)**
5. [HIGH - I/O & MEMORY] **Duplicazione massiva e letture su disco bloccanti di log giganti nella pipeline di sblocco**
6. [HIGH - MATH ERROR] **Calcolo errato delle commissioni di uscita basato sul prezzo di ingresso nel loop Live**
7. [MEDIUM - DESIGN] **Inconsistenza metodologica di simulazione della friction tra Backtest e Live**
8. [MEDIUM - SYSTEMS] **Crescita illimitata dei file di registro (Mancanza di rotazione dei log)**
9. [MEDIUM - STRATEGY] **Inflazione artificiale del punteggio dei pattern di candele per segnali opposti simultanei**
10. [MEDIUM - STRATEGY] **Classificazione debole (sotto-filtrata) dei pattern Morning e Evening Star**
11. [MEDIUM - CONFIG] **Inconsistenza nel dimensionamento della posizione dovuto a mismatch del tasso di commissione**
12. [LOW - CLEAN CODE] **Iper-ingegnerizzazione architetturale ed esplosione delle importazioni (Spaghetti Architecture)**
13. [LOW - STRATEGY] **Sovrapposizione indiscriminata della prossimità a Supporto e Resistenza nel motore di setup**

---

## 1. 🔴 [CRITICAL - PORTABILITY] Crash da codifica caratteri non-ASCII su terminali Windows
* **File coinvolti**: `trading_bot/test_execution_model.py`, `trading_bot/test_risk_engine.py` e vari script di diagnostica.
* **Categoria**: Compatibilità OS / Robustezza del Codice.
* **Descrizione**:
  Negli script di test e diagnostica sono stati inseriti caratteri grafici Unicode box-drawing (es. `─` ossia `\u2500` o frecce `→` ossia `\u2192`). 
  Su sistemi Windows con codifiche regionali non-UTF-8 (come il codepage italiano `cp1252`), l'esecuzione diretta degli script tramite il prompt dei comandi standard (`cmd` o `powershell`) causa un immediato crash fatale con errore:
  `UnicodeEncodeError: 'charmap' codec can't encode characters in position 4-5: character maps to <undefined>`.
* **Impatto**:
  Gli script di test e alcune pipeline diagnostiche falliscono istantaneamente l'esecuzione su macchine Windows regionali, a meno che non si forzi esplicitamente la modalità UTF-8 tramite opzioni interprete come `python -X utf8` o variabili d'ambiente.
* **Soluzione Raccomandata**:
  Sostituire tutti i caratteri grafici box-drawing non-ASCII con caratteri standard ASCII compatibili (`-`, `=`, `>`, `|`) o intercettare le eccezioni di codifica configurando `sys.stdout` all'avvio con `sys.stdout.reconfigure(encoding="utf-8")`.

---

## 2. 🔴 [CRITICAL - RISK] Stato di VaR obsoleto (off-by-one) nei Flag di Concentrazione del Portafoglio
* **File coinvolti**: `trading_bot/core/portfolio_risk_engine.py` (riga 241 e righe 334-337)
* **Categoria**: Gestione del Rischio / Logica Quantitativa.
* **Descrizione**:
  Il metodo `snapshot()` calcola i flag di concentrazione chiamando `self._concentration_flags(exposures, corr_matrix)` alla riga 241, *prima* che il nuovo snapshot appena calcolato venga aggiunto alla coda storica (cosa che avviene alla riga 257 tramite `self.snapshots.append(snapshot)`).
  All'interno di `_concentration_flags()`, il controllo sul superamento del limite del Value at Risk (VaR) è implementato come segue:
  ```python
  latest_var = self.snapshots[-1].portfolio_var if self.snapshots else 0.0
  if latest_var > self.balance * self.manager.var_limit_pct:
      flags.append("VAR_LIMIT_EXCEEDED")
  ```
  Poiché il metodo interroga `self.snapshots[-1]`, esso sta leggendo il VaR calcolato sul tick *precedente* e non quello corrente!
* **Impatto**:
  1. Durante il primo trade assoluto, non essendoci snapshot in coda, il VaR corrente viene ignorato e impostato a `0.0`, lasciando il sistema cieco a violazioni immediate.
  2. Nei tick successivi, il segnale `VAR_LIMIT_EXCEEDED` viene attivato con un ritardo di 1 tick (ritardo di lag temporale). Se un trade improvviso fa saltare il VaR oltre i limiti massimi consentiti, il bot lo rileva solo al tick successivo, esponendo il capitale a un potenziale over-exposure non controllato.
* **Soluzione Raccomandata**:
  Modificare la firma di `_concentration_flags()` per accettare direttamente il valore `portfolio_var` corrente appena calcolato all'interno del metodo `snapshot()`, eliminando il riferimento a `self.snapshots[-1]`.

---

## 3. 🟠 [HIGH - CONCURRENCY] Blocco del processo di chiusura asincrono in modalità `--once`
* **File coinvolti**: `trading_bot/run_paper_trading.py`, `trading_bot/core/paper_engine.py`, `trading_bot/core/telegram_control.py`
* **Categoria**: Gestione Risorse Asincrone / Concorrenza.
* **Descrizione**:
  Il bot introduce il modulo `TelegramControlBot` che istanzia un listener a lungo termine per il polling dei comandi (`poll_forever`). Quando il bot viene avviato in modalità single-loop (`--once`), al termine del ciclo di trading viene inviato un segnale di cancellazione al task Telegram (`tg_task.cancel()`). 
  Tuttavia, `aiohttp.ClientSession` mantiene attivi pool di connessioni socket interni. Poiché la sessione client o i connettori sottostanti non vengono chiusi in modo pulito e deterministico, l'event loop di `asyncio` rimane attivo in attesa del rilascio dei socket.
* **Impatto**:
  Il processo Python rimane bloccato ("hang") all'infinito dopo aver completato il ciclo di trading, impedendo la chiusura dello script. Gli sviluppatori hanno dovuto implementare una patch di watchdog che forza la chiusura brutale con `os._exit(0)`, che nasconde il leak delle risorse invece di risolverlo alla radice.
* **Soluzione Raccomandata**:
  Chiedere la chiusura ordinata di `ClientSession` richiamando il metodo `.close()` in una fase di teardown strutturata del bot (es. nel blocco `finally` di `run_paper_trading.py` o `main.py`).

---

## 4. 🟠 [HIGH - ML LOGIC] Glitch logico nel meccanismo di auto-addestramento dell'AI
* **File coinvolti**: `trading_bot/core/ai_engine.py` (riga 328) e `core/meta_labeling.py`
* **Categoria**: Logic Bug / Machine Learning.
* **Descrizione**:
  La logica di riaddestramento automatico del modello AI è basata su una corrispondenza modulo rigorosa:
  ```python
  if lines >= Config.AI_MIN_SAMPLES and lines % Config.AI_RETRAIN_EVERY == 0:
      self.train(csv_path)
  ```
  Se il file dei campioni cresce oltre una determinata soglia e, a causa di salvataggi multipli, concorrenza o accodamenti simultanei, il numero di righe salta un valore esatto (ad esempio, passa da 999 a 1001 saltando la riga 1000 quando `AI_RETRAIN_EVERY = 500`), la condizione di modulo non sarà mai più soddisfatta.
* **Impatto**:
  Il bot fallisce silenziosamente l'auto-riaddestramento continuo dell'AI. Il modello rimarrà statico, ignorando i nuovi dati di mercato raccolti e portando a un inevitabile degrado delle prestazioni (model drift) in regimi di mercato mutati.
* **Soluzione Raccomandata**:
  Tracciare l'indice o il numero di campioni dell'ultimo addestramento completato con successo (es. memorizzandolo in un file di configurazione di stato o nei metadati del modello) e avviare il retrain non appena `campioni_correnti - campioni_ultimo_addestramento >= Config.AI_RETRAIN_EVERY`.

---

## 5. 🟠 [HIGH - I/O & MEMORY] Duplicazione helper e letture disk ricorsive bloccanti di log giganti
* **File coinvolti**: Tutti i moduli `paper_unlock_*.py` (in particolare `paper_unlock_supervised_execution.py`, `paper_unlock_observation.py`, `paper_order_leakage_guard.py` e `paper_once_runner_footer.py`)
* **Categoria**: Efficienza Computazionale / I/O Disistimato.
* **Descrizione**:
  Questi moduli riproducono localmente e in maniera ridondante la funzione di lettura log `_iter_jsonl_events` (o `_read_jsonl`):
  ```python
  def _iter_jsonl_events(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
      ...
      lines = p.read_text(encoding="utf-8").splitlines()
  ```
  Questa implementazione esegue una `p.read_text()` sincrona che carica l'INTERO file dei log di eventi (`paper_events.jsonl`) in memoria, lo spezza per righe e solo successivamente filtra le ultime righe.
* **Impatto**:
  1. **Memory Leak e CPU Freeze**: In sessioni a lungo termine, `paper_events.jsonl` può crescere fino a centinaia di megabyte o gigabyte. Caricare e spezzare sincronamente un simile volume di testo nel thread primario a ogni tick congela l'event loop di asyncio (blip-lag) e causa picchi insostenibili di RAM.
  2. **I/O Ridondante**: Poiché circa 20 script diagnostici vengono eseguiti in sequenza a ogni ciclo del bot, il file `paper_events.jsonl` viene letto e scansionato da zero **20 volte consecutive per tick**, distruggendo le prestazioni di I/O del disco.
* **Soluzione Raccomandata**:
  1. Unificare l'accesso in lettura dei log. Il log degli eventi dovrebbe essere letto una singola volta all'inizio del ciclo di tick e passato come lista immutabile in memoria a tutti i moduli di diagnostica interessati.
  2. Implementare un parser di log efficiente basato su generatori o lettura a ritroso del file (`reverse-line reader`), evitando di caricare l'intera storia immutata ad ogni tick.

---

## 6. 🟠 [HIGH - MATH ERROR] Calcolo errato delle commissioni di uscita basato sul prezzo di ingresso nel loop Live
* **File coinvolti**: `trading_bot/main.py` (riga 309, 366, 430)
* **Categoria**: Logica di Calcolo PnL / Trading Engine.
* **Descrizione**:
  Nel monitoraggio live delle posizioni in `main.py`, le commissioni di uscita per i target TP1, TP2 o SL vengono calcolate utilizzando il prezzo di *ingresso* (`entry`) anziché l'effettivo prezzo di *uscita* (`tp1`, `tp2`, `sl`):
  ```python
  comm_1 = (size / 2) * entry * COMMISSION_RATE * 2
  comm_2 = (size / 2) * entry * COMMISSION_RATE * 2
  ```
  In realtà, la commissione di un ordine di vendita/acquisto a mercato o limite viene addebitata dall'exchange sul controvalore effettivo al momento del fill (prezzo di uscita).
* **Impatto**:
  1. Per i trade vincenti ad alto RR (Reward-to-Risk), dove il prezzo di uscita è molto più alto di quello di ingresso, le commissioni reali pagate sono significativamente superiori a quelle stimate.
  2. Questo introduce un errore cumulativo costante nel saldo simulato (`balance_live.txt`). Nel lungo termine, si verificherà una divergenza (drift) non trascurabile tra il saldo calcolato dal bot e il saldo reale presente sull'exchange.
* **Soluzione Raccomandata**:
  Modificare il calcolo delle commissioni di chiusura per riflettere il prezzo effettivo di esecuzione (es. `exit_price`):
  ```python
  comm_1 = (size / 2) * tp1 * COMMISSION_RATE * 2
  ```

---

## 7. 🟡 [MEDIUM - DESIGN] Inconsistenza metodologica di simulazione della friction tra Backtest e Live
* **File coinvolti**: `trading_bot/backtest_lab.py`, `trading_bot/core/risk.py`, `trading_bot/core/slippage_model.py`
* **Categoria**: Metodologia Quant / Design.
* **Descrizione**:
  In modalità Live/Paper trading, il bot simula lo slippage in tempo reale modificando dinamicamente il prezzo effettivo di fill prima di valutare la validità del trade, la dimensione della posizione (commission-aware sizing) e il monitoraggio di Stop-Loss (SL) e Take-Profit (TP). 
  Nel motore di backtest (`backtest_lab.py`), lo slippage non viene simulato lungo il percorso dei prezzi. Il trade entra ed esce al prezzo teorico esatto (senza alterare la distanza SL/TP) e solo *ex-post* (dopo la chiusura del trade) viene calcolato un costo di esecuzione teorico dal modulo `ExecutionCostModel` detraendolo dal PnL monetario complessivo.
* **Impatto**:
  Questo approccio introduce una forte discrepanza tra i test storici e le performance reali. In live trading lo slippage può anticipare il trigger di uno stop-loss o negare il tocco di un take-profit a causa del prezzo di esecuzione peggiorato; in backtest questo effetto geometrico viene ignorato, producendo metriche storiche artificialmente ottimistiche ed esiti di trade non speculari.
* **Soluzione Raccomandata**:
  Unificare la logica di simulazione del trade. Il motore di backtest dovrebbe applicare lo slippage direttamente sul prezzo di ingresso e di uscita del trade (adeguando geometricamente i livelli fisici di SL e TP) prima di simulare l'evoluzione candela per candela, replicando esattamente il comportamento del motore live.

---

## 8. 🟡 [MEDIUM - SYSTEMS] Crescita illimitata dei file di registro (Mancanza di rotazione dei log)
* **File coinvolti**: `trading_bot/main.py`, `trading_bot/multi_trade_manager.py`, `data/paper_events.jsonl`
* **Categoria**: Infrastruttura / I/O File.
* **Descrizione**:
  Le scritture dei log in `main.py` e `multi_trade_manager.py` avvengono tramite chiamate dirette standard a `open(log_file, "a")` per appendere stringhe di testo. Non esiste alcuna implementazione di un sistema di gestione strutturato come `logging` con gestori rotativi (`RotatingFileHandler` o `TimedRotatingFileHandler`).
* **Impatto**:
  In una modalità di trading live o paper a lungo termine (che gira 24/7 per settimane o mesi), i file di log come `bot_live.log` e `paper_events.jsonl` cresceranno indefinitamente di dimensioni fino a saturare completamente lo spazio di archiviazione su disco della macchina host, portando a crash improvvisi del sistema e corruzione dei file. Inoltre, la scansione di file JSONL di grandi dimensioni rallenterà le prestazioni complessive del bot.
* **Soluzione Raccomandata**:
  Sostituire gli append testuali diretti con il modulo nativo `logging` di Python, configurando un `RotatingFileHandler` con un limite di dimensione massima del file (es. 10MB) e un numero massimo di file di backup storici da conservare (es. 5 file).

---

## 9. 🟡 [MEDIUM - STRATEGY] Inflazione artificiale del punteggio dei pattern di candele per segnali opposti simultanei
* **File coinvolti**: `trading_bot/core/candlestick_patterns.py` (righe 333-337 e righe 418-420)
* **Categoria**: Logica di Strategia / Signal Processing.
* **Descrizione**:
  Durante il calcolo del punteggio cumulativo del pattern di candele (`pattern_score`), il sistema aggiunge incondizionatamente punti se vengono rilevati pattern rialzisti o ribassisti:
  ```python
  if bullish:
      score += 35.0 + min(20.0, 5.0 * len(set(bullish)))
  if bearish:
      score += 35.0 + min(20.0, 5.0 * len(set(bearish)))
  ```
  Se su una singola candela sono presenti contemporaneamente sia pattern fortemente rialzisti che fortemente ribassisti (es. una candela molto volatile e incerta che soddisfa i criteri di wicks opposti o pin-bar ambigue), entrambi i blocchi sommano il loro punteggio.
* **Impatto**:
  Questo genera un'inflazione del punteggio (`pattern_score` sale oltre 75/100, indicando estrema confidenza) su candele che in realtà mostrano uno stato di incertezza bilaterale totale. Il bot considererà questa candela come un segnale ad altissima qualità anziché filtrarla come neutrale, portando a sblocchi o entrate su setups degradati.
* **Soluzione Raccomandata**:
  Introdurre un fattore di penalizzazione o decremento del punteggio proporzionale alla presenza di segnali contrastanti. Se sia `bullish` che `bearish` contengono pattern attivi, il punteggio finale dovrebbe essere ridotto a un livello minimo di cautela (es. fisso a `0` o limitato al valore neutrale `15`).

---

## 10. 🟡 [MEDIUM - STRATEGY] Classificazione debole e sotto-filtrata dei pattern Morning/Evening Star
* **File coinvolti**: `trading_bot/core/candlestick_patterns.py` (riga 274)
* **Categoria**: Logica di Strategia / Pattern Recognition.
* **Descrizione**:
  I pattern Morning Star ed Evening Star (a 3 candele) richiedono che la prima candela della struttura sia un forte trend direzionale (bearish per Morning Star, bullish per Evening Star). 
  Il codice implementa questo controllo come segue:
  ```python
  is_p2_trend = prev2_stats["body_ratio"] >= settings.min_body_ratio
  ```
  Tuttavia, `settings.min_body_ratio` è impostato a un valore estremamente permissivo pari a `0.25` (il corpo copre solo il 25% dell'intervallo High-Low, lasciando il 75% del range alle wicks/ombre).
* **Impatto**:
  Questa soglia troppo bassa consente di considerare candele deboli, doji, hammer o strutture di consolidamento ad alta volatilità bilaterale come "forti candele di trend iniziale". Ciò diluisce drasticamente il valore predittivo e statistico del pattern Morning/Evening Star, portando a frequenti falsi segnali di inversione in mercati laterali e rumorosi.
* **Soluzione Raccomandata**:
  Modificare il controllo per utilizzare il parametro di corpo forte `strong_body_ratio` (impostato di default a `0.55` o 55% del range totale) per qualificare la prima candela:
  ```python
  is_p2_trend = prev2_stats["body_ratio"] >= settings.strong_body_ratio
  ```

---

## 11. 🟡 [MEDIUM - CONFIG] Inconsistenza nel dimensionamento dovuto al mismatch del tasso di commissione
* **File coinvolti**: `trading_bot/core/paper_engine.py` (riga 234) vs `core/risk.py` (riga 526)
* **Categoria**: Configurazione / Integrità dei Parametri.
* **Descrizione**:
  Il modulo `PaperTradingEngine` istanzia il `PaperBroker` forzando un tasso di commissione raddoppiato per simulare gli ordini a mercato (taker):
  ```python
  self.broker = PaperBroker(..., fee_rate=Config.COMMISSION_RATE * 2.0, ...)
  ```
  Tuttavia, il modulo di risk sizing `DynamicRiskEngine` calcola le dimensioni delle posizioni tramite la formula *commission-aware* utilizzando il valore standard non raddoppiato memorizzato in `Config.COMMISSION_RATE` (pari di default a `0.0002`):
  ```python
  commission = commission if commission is not None else Config.COMMISSION_RATE
  ```
* **Impatto**:
  La formula del dimensionamento calcola la dimensione ottimale ipotizzando che la transazione costi la metà di quanto effettivamente addebitato dal `PaperBroker` su ogni esecuzione. Questo causa un mismatch costante tra il rischio teorico previsto dall'algoritmo di Kelly e il rischio reale esposto sul mercato, portando a leggeri sovradimensionamenti delle posizioni.
* **Soluzione Raccomandata**:
  Allineare i parametri di commissione live. Il `DynamicRiskEngine` dovrebbe ricevere nel metodo `size_position()` il tasso di commissione corretto e raddoppiato (corrispondente al taker fee di `0.0004` / 4 bps) per allineare al millesimo la matematica del sizing con le detrazioni reali del broker.

---

## 12. 🟢 [LOW - CLEAN CODE] Iper-ingegnerizzazione ed esplosione delle importazioni (Spaghetti Architecture)
* **File coinvolti**: `trading_bot/core/paper_engine.py` (righe 31-88) e tutti i moduli `paper_unlock_*.py`
* **Categoria**: Architettura Software / Manutenibilità.
* **Descrizione**:
  Il modulo principale `paper_engine.py` presenta un blocco di circa 30 importazioni consecutive per gestire ogni singolo aspetto di diagnostica, preflight, audit e report introdotto dalle varie patch incrementali (da `paper_unlock_profile_refinement` fino a `paper_unlock_supervised_execution` e `paper_order_leakage_guard`).
  Inoltre, il metodo `write_performance_artifacts()` richiama sequenzialmente e incondizionatamente tutti questi report su ogni singolo ciclo di valutazione, delegando la logica di blocco/abilitazione solo a controlli interni delle singole funzioni.
* **Impatto**:
  Questo design rappresenta un notevole "code smell". Aumenta il tempo di startup e il consumo di memoria del bot a causa del caricamento in memoria di decine di moduli, incrementa il rischio di dipendenze circolari e rende la manutenzione del codice estremamente complessa. L'architettura assomiglia a una sequenza rigida di patch storiche cablate invece di un sistema a plugin o eventi pulito.
* **Soluzione Raccomandata**:
  Creare un sistema di registrazione dei diagnostici a plugin o a registro. Ciascun modulo di diagnostica dovrebbe registrarsi presso un gestore centrale (`ReportRegistry`), consentendo al `PaperTradingEngine` di iterare dinamicamente sui report attivi in modo disaccoppiato e pulito.

---

## 13. 🟢 [LOW - STRATEGY] Sovrapposizione indiscriminata di Supporto e Resistenza nel motore di setup
* **File coinvolti**: `trading_bot/core/setup_engine.py` (righe 401-402)
* **Categoria**: Logica di Strategia / Mean Reversion.
* **Descrizione**:
  Nel calcolo del punteggio per il setup di mean reversion (`_ranging_mean_reversion`), se le chiavi specifiche `near_support` o `near_resistance` non sono fornite nel record storicizzato, entrambe le variabili ripiegano incondizionatamente sullo stesso indicatore generico `near_sr`:
  ```python
  near_support = cls._b(row, "near_support", False) or cls._f(row, "near_sr", 0.0) > 0
  near_resistance = cls._b(row, "near_resistance", False) or cls._f(row, "near_sr", 0.0) > 0
  ```
* **Impatto**:
  Se `near_sr` è positivo (il prezzo è vicino a uno dei due livelli generici di S/R), sia `near_support` che `near_resistance` vengono impostate contemporaneamente a `True`. Ciò gonfia artificialmente sia il punteggio BUY (che cerca supporto) sia il punteggio SELL (che cerca resistenza) contemporaneamente, diluendo drasticamente l'orientamento direzionale del setup di reversion.
* **Soluzione Raccomandata**:
  Utilizzare la posizione relativa all'interno delle bande o il prezzo rispetto alla mediana per discriminare quale delle due variabili valorizzare quando `near_sr` è positivo (es. impostare `near_support = True` solo se il prezzo si trova anche nella metà inferiore del range di Bollinger).

---

### Conclusioni dell'Audit Generale
La stabilità logica e il superamento dei test unitari confermano l'eccellente robustezza del bot. Tuttavia, la presenza di **bug quantitativi occulti** (come lo **stale VaR nei flag di portafoglio**, il **mismatch delle commissioni di Kelly** e il **calcolo errato delle commissioni di uscita**) e di **colli di bottiglia architetturali bloccanti** (come le **ri-letture sincrone ricorsive dei log giganti**) evidenzia aree fondamentali da correggere per garantire un'operatività live 24/7 affidabile, performante e priva di deriva monetaria.
