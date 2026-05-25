# 🔍 AUDIT SU PATTERN CANDLE, PROBABILITÀ E PARAMETRI CANDIDATI (AGGIORNATO)

Questo report contiene un'analisi approfondita e mirata sui moduli che governano:
1. Il rilevamento dei **pattern di candele** (`candlestick_patterns.py`)
2. La calibrazione delle **probabilità predette** (`calibration.py`)
3. I **parametri e filtri** per abilitare i candidati operativi (`paper_unlock_gate.py` / `paper_engine.py`)

L'audit ha evidenziato **7 problemi significativi** legati ai pattern e alle probabilità, che minano la precisione dei segnali, l'adattamento delle probabilità e la coerenza del capitale di rischio.

---

## 🗺️ INDICE DELLE CRITICITÀ RILEVATE

1. [HIGH - LOGIC BUG] **Classificazione conflittuale nei pattern a candela singola (Doji / High Wave)**
2. [HIGH - LOGIC BUG] **Definizione errata e permissiva di Engulfing Bullish/Bearish**
3. [MEDIUM - CONFIG BUG] **Vincolo rigido (Hardcoded) sul nome del profilo in `paper_unlock_gate.py`**
4. [MEDIUM - STATISTICAL] **Degrado della calibrazione e sbilanciamento del sizing di Kelly in tempo reale**
5. [MEDIUM - STRATEGY] **Inflazione artificiale del punteggio per segnali opposti simultanei (Doji ad ampio range)**
6. [MEDIUM - STRATEGY] **Classificazione debole e sotto-filtrata dei pattern Morning e Evening Star**
7. [MEDIUM - CONFIG] **Mismatch del tasso di commissione nel dimensionamento di Kelly rispetto al Paper Broker**

---

## 1. 🔴 [HIGH - LOGIC BUG] Classificazione conflittuale nei pattern a candela singola
* **File coinvolto**: `trading_bot/core/candlestick_patterns.py`
* **Descrizione**:
  I pattern a singola candela *Hammer* (rialzista) e *Shooting Star* (ribassista) sono rilevati analizzando la lunghezza dell'ombra rispetto al corpo.
  Tuttavia, il codice non applica limitazioni sulla wick opposta per questi pattern. Ad esempio, una candela con un corpo piccolissimo (Doji) che presenta un'ombra inferiore lunghissima soddisferà i criteri di Hammer, ma se ha anche un'ombra superiore altrettanto lunga, in realtà è una *High Wave* o una candela di indecisione bilaterale estrema, non un Hammer.
* **Impatto**:
  Candele ad altissima indecisione vengono erroneamente classificate come pattern direzionali forti, sporcando il dataset delle features ML e inducendo in errore il classificatore.
* **Soluzione Raccomandata**:
  Imporre limiti massimi rigorosi sulla wick opposta (es. `upper_wick_ratio <= 0.10` per Hammer, e `lower_wick_ratio <= 0.10` per Shooting Star), assicurando che la pin-bar sia realmente asimmetrica e direzionale.

---

## 2. 🔴 [HIGH - LOGIC BUG] Definizione errata e permissiva di Engulfing Bullish/Bearish
* **File coinvolto**: `trading_bot/core/candlestick_patterns.py`
* **Descrizione**:
  La definizione quantitativa standard di un pattern Engulfing richiede che il corpo della candela corrente contenga interamente (superi) il range totale (High-Low) o almeno il corpo della candela precedente. 
  Il codice originale controllava semplicemente che la chiusura corrente superasse l'apertura precedente. Questo classificava erroneamente come "Engulfing" candele molto piccole che non coprivano affatto l'intervallo reale precedente.
* **Impatto**:
  Generazione sistematica di falsi segnali di inversione (Engulfing fantasma) durante micro-consolidazioni piatte.
* **Soluzione Raccomandata**:
  Rendere il controllo rigoroso introducendo una richiesta di espansione minima del corpo (es. `body > prev_body * 1.05`) e un contro-controllo di avvolgimento reale dei limiti corporei.

---

## 3. 🟡 [MEDIUM - CONFIG BUG] Vincolo rigido (Hardcoded) sul nome del profilo in `paper_unlock_gate.py`
* **File coinvolti**: `trading_bot/core/paper_unlock_gate.py` (righe 34 e successivi)
* **Descrizione**:
  Nel modulo che gestisce il filtro di sblocco temporaneo per testare i candidati respinti dal bot (`evaluate_paper_unlock`), il nome del profilo abilitato è rigidamente cablato su `"BTC_ONLY_40_Q60"`. Se l'operatore modifica questo profilo in `.env` impostando ad esempio `"ETH_ONLY_50_Q70"`, le valutazioni continuano ad essere associate al vecchio profilo.
* **Impatto**:
  Mancata flessibilità e impossibilità di implementare configurazioni dinamiche per asset diversi o test paralleli multi-asset senza ricompilare il codice.
* **Soluzione Raccomandata**:
  Leggere dinamicamente il parametro `profile` direttamente dalle impostazioni passate in input all'istanziazione dell'engine, rimuovendo la stringa statica cablata a livello di classe.

---

## 4. 🟡 [MEDIUM - STATISTICAL] Degrado della calibrazione e sbilanciamento del sizing di Kelly in tempo reale
* **File coinvolti**: `trading_bot/core/calibration.py` (riga 257) e `core/risk.py`
* **Descrizione**:
  Il dimensionamento scientifico del capitale tramite Kelly si affida completamente alla precisione delle probabilità calibrate restituite da `ProbabilityCalibrator`. 
  Tuttavia, in tempo reale, se il numero di campioni di calibrazione scende sotto i 40 (es. a causa di un embargo temporale), il sistema disabilita silenziosamente la calibrazione impostando il metodo a `"none"`.
* **Impatto**:
  In assenza di calibrazione, il bot utilizza le probabilità grezze ("raw") del modello ad albero, che tendono a essere sovra-ottimistiche (es. 85-90%). Kelly interpreterà queste probabilità come un "vantaggio eccezionale", portando a un sovradimensionamento aggressivo delle posizioni (overleveraging) che incrementa drasticamente il drawdown.
* **Soluzione Raccomandata**:
  - Implementare un calibratore globale di fallback (pre-addestrato offline) da utilizzare qualora i dati di calibrazione locale in tempo reale siano insufficienti.
  - Ridurre drasticamente la frazione di Kelly (es. portandola da Half-Kelly a Quarter-Kelly, `0.25`) qualora `is_calibrated` del report sia `False`.

---

## 5. 🟡 [MEDIUM - STRATEGY] Inflazione artificiale del punteggio per segnali opposti simultanei
* **File coinvolto**: `trading_bot/core/candlestick_patterns.py` (righe 333-337)
* **Descrizione**:
  Il punteggio cumulativo del pattern di candele (`pattern_score`) somma incondizionatamente punteggi positivi se vengono rilevati pattern rialzisti o ribassisti:
  ```python
  if bullish:
      score += 35.0 + min(20.0, 5.0 * len(set(bullish)))
  if bearish:
      score += 35.0 + min(20.0, 5.0 * len(set(bearish)))
  ```
  Se una candela soddisfa contemporaneamente criteri rialzisti e ribassisti (es. una candela ad altissimo range ma indecisa), entrambi i blocchi accumulano punti.
* **Impatto**:
  La candela riceve un punteggio elevato (es. 75/100, indicando forte affidabilità) quando in realtà rappresenta il culmine dell'indecisione di mercato. Ciò inganna il filtro di sblocco diagnostico e la classificazione di qualità del setup.
* **Soluzione Raccomandata**:
  Introdurre un blocco condizionale: se sono presenti sia pattern `bullish` che `bearish`, resettare il punteggio o limitarlo a un valore di indecisione neutrale (es. `15.0`), riflettendo lo stato di stallo dei prezzi.

---

## 6. 🟡 [MEDIUM - STRATEGY] Classificazione debole e sotto-filtrata dei pattern Morning e Evening Star
* **File coinvolto**: `trading_bot/core/candlestick_patterns.py` (riga 274)
* **Descrizione**:
  Morning Star ed Evening Star (pattern a 3 candele) richiedono che la prima candela della struttura sia una candela di trend decisa.
  Il codice controlla la forza di questa candela con `is_p2_trend = prev2_stats["body_ratio"] >= settings.min_body_ratio`, dove `min_body_ratio` è impostato a un permissivo `0.25`.
* **Impatto**:
  Una candela con un corpo microscopico (25%) e ombre enormi (75%) viene qualificata come candela di trend direzionale iniziale, portando alla classificazione di Morning/Evening star fittizie su aree di mero rumore laterale.
* **Soluzione Raccomandata**:
  Richiedere che la prima candela della struttura rispetti la soglia corporea forte `strong_body_ratio` (pari a `0.55` o 55% del range totale), garantendo la reale forza direzionale iniziale del pattern.

---

## 7. 🟡 [MEDIUM - CONFIG] Mismatch del tasso di commissione nel dimensionamento di Kelly
* **File coinvolti**: `trading_bot/core/paper_engine.py` (riga 234) vs `core/risk.py` (riga 526)
* **Descrizione**:
  `PaperTradingEngine` istanzia il `PaperBroker` raddoppiando il tasso di commissione standard per simulare gli ordini a mercato (taker fee di 4 bps / `0.0004`):
  ```python
  self.broker = PaperBroker(..., fee_rate=Config.COMMISSION_RATE * 2.0, ...)
  ```
  Tuttavia, il calcolo della dimensione della posizione basato su Kelly nel `DynamicRiskEngine` ripiega per default sul valore standard a 2 bps (`Config.COMMISSION_RATE` = `0.0002`):
  ```python
  commission = commission if commission is not None else Config.COMMISSION_RATE
  ```
* **Impatto**:
  L'algoritmo di risk sizing calcola la dimensione ottimale ipotizzando commissioni inferiori a quelle realmente applicate dal broker per ogni operazione di fill. Questo causa lievi errori di sovradimensionamento quantitativo del capitale rispetto all'edge atteso al netto dei costi.
* **Soluzione Raccomandata**:
  Garantire l'allineamento dei parametri di rete passando esplicitamente al modulo di risk sizing il tasso taker corretto e raddoppiato (`0.0004` / 4 bps), unificando l'aspettativa di costo con l'addebito reale del broker.

---

### Conclusioni dell'Audit sulle Candele e sulle Probabilità
I moduli diagnostici dei pattern e della calibrazione sono strutturalmente avanzati, ma risentono di piccoli **difetti logici di sovrapposizione e sotto-filtraggio**. L'integrazione di filtri asimmetrici sulle ombre, l'innalzamento della soglia corporea iniziale delle stelle a 3 candele e l'allineamento matematico delle commissioni Kelly-Broker elimineranno i falsi sblocchi diagnostici e ottimizzeranno al millesimo la resa probabilistica del trading bot!
