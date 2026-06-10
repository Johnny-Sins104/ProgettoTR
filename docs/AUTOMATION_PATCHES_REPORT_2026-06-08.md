# Report patch dalla comunicazione automatica

**Data audit:** 2026-06-08
**Periodo:** dall'avvio del ciclo automatico Claude Code -> Codex
**Fonte:** roadmap, prompt archiviati, manifest SHA-256, report Claude e review Codex

## Stato sintetico

| Patch | Stato | Cicli automatici | Ultimo esito verificato |
|---|---|---:|---|
| TR-INT-02B | Approvata | 2 | Codex PASS; 128 test mirati e 1125 test completi |
| TR-INT-03 | In correzione | 2/3 | Codex ha richiesto 2 fix riprodotti; Claude sta applicando il ciclo 2 |
| TR-INT-04 | Non iniziata | 0 | Attende approvazione TR-INT-03 |
| TR-INT-05 | Non iniziata | 0 | Attende TR-INT-04 |
| TR-OPS-01 | Non iniziata | 0 | Attende TR-INT-05 |

## TR-INT-02B - Execution correctness hotfix

**Stato:** approvata da Codex.

### Correzioni principali

- Eliminato il fill paper retrodatato nello stesso ciclo del segnale.
- Il pending viene persistito prima del fill e riempito solo in un ciclo successivo.
- Aggiunto controllo SL/TP sulla candela di ingresso.
- UnifiedCostModel ora fallisce in modo chiuso: nessun fallback silenzioso a costo zero.
- I segnali SELL nel clean paper long-only vengono rifiutati esplicitamente e registrati.
- Stato JSON corrotto blocca il ciclo senza sovrascrivere il file o aprire posizioni.
- Default rischio clean portato a `0.005` anche nelle CLI residue.
- Unificata la validazione entry-gap tra backtest e paper.

### File modificati nell'ultimo ciclo automatico

- `tools/clean_bot_backtest.py`
- `tools/clean_bot_optimizer.py`
- `trading_bot/clean_bot/paper_live.py`
- `trading_bot/tests/test_clean_bot_int02b.py`

### Verifica Codex

- Test mirati: `128 passed`.
- Suite completa: `1125 passed`.
- Warning: 4 diagnostici preesistenti.
- Esito: **PASS**.

Report dettagliato: `docs/TR_INT_02B_HOTFIX_REPORT.md`.

## TR-INT-03 - Closed-candle WebSocket feed

**Stato:** in correzione, ciclo automatico 2/3.

### Prima implementazione Claude

Creati:

- `trading_bot/clean_bot/market_feed_ws.py`
- `trading_bot/tests/test_market_feed_ws.py`
- `docs/TR_INT_03_REPORT.md`

Funzioni implementate:

- Feed pubblico Binance senza chiavi private.
- Elaborazione delle sole candele chiuse.
- Deduplicazione tramite timestamp di chiusura.
- Timeout zombie di 90 secondi.
- Bootstrap storico REST.
- Watermark multi-timeframe con stato esplicito.
- Metriche health.
- `FEED_ENABLED=False` e nessuna rete all'import.

Claude ha dichiarato:

- Test mirati: `16/16 passed`.
- Suite completa: `1141 passed`.

### Review indipendente Codex - ciclo 1

Codex ha riprodotto due problemi non coperti dai test iniziali:

1. Il contatore del backoff veniva azzerato appena il socket si apriva. Connessioni
   aperte e cadute immediatamente producevano delay `[1.0, 1.0, 1.0]` invece di
   un backoff esponenziale.
2. Un errore nel bootstrap REST veniva assorbito e il feed tentava comunque la
   connessione WebSocket, violando il comportamento fail-closed.

Esito Codex: **fix_required**. La suite completa non è stata rieseguita da Codex
nel ciclo 1 perché i casi critici mirati erano falliti.

### Correzioni ciclo 2 in corso

Claude sta applicando esclusivamente i fix richiesti:

- azzeramento del backoff solo dopo la prima ricezione riuscita;
- errore REST propagato per impedire qualsiasi tentativo WebSocket;
- nuovo test per drop immediati ripetuti;
- nuovo test per bootstrap REST fallito con zero tentativi WebSocket;
- aggiornamento del report e riesecuzione dei test.

`TR-INT-03` sarà considerata completata solo dopo una nuova approvazione Codex.

## Correzioni dell'automazione

Queste modifiche riguardano il coordinatore, non la logica di trading:

- Creata roadmap canonica: l'automazione esegue solo patch esplicitamente definite.
- Aggiunto passaggio diretto Claude -> Codex -> Claude.
- Aggiunti manifest SHA-256 dei file cambiati per ogni ciclo.
- Aggiunta barriera quota con ripresa delle sessioni interrotte.
- Corretto riconoscimento del messaggio Claude `session limit`.
- Corretto il prompt roadmap che PowerShell deformava interpretando i backtick.
- Aggiunta validazione completa della roadmap e comando `-RoadmapPreview`.
- Migliorato il monitor live con patch corrente e prossima patch.
- Configurata la review Codex con sandbox compatibile con Windows.
- Aggiunto retry automatico per errori ambientali della review Codex.
- Conservato il vincolo: Codex revisiona e genera fix per Claude, ma non modifica
  direttamente il codice prodotto durante il ciclo automatico.

## Incidenti gestiti

| Incidente | Risoluzione |
|---|---|
| Claude ha raggiunto il limite sessione durante TR-INT-03 | Sessione e lavoro conservati; ripresa automatica alle 05:00 |
| Prima review Codex bloccata da `windows sandbox: spawn setup refresh` | Sandbox Codex resa compatibile e review rilanciata |
| Warning plugin/skill Codex | Confermati non bloccanti e non collegati a ProgettoTR |

## Prossimi passaggi automatici

1. Claude completa i due fix verificati di TR-INT-03.
2. Codex esegue nuova review e test indipendenti.
3. Se approvata, TR-INT-03 viene marcata completata e parte TR-INT-04.
4. Se restano difetti, Codex invia a Claude un ultimo prompt mirato, fino al
   limite massimo di 3 cicli.

Trading live, API private e ordini reali restano disabilitati.
