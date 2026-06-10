# Claude Code + Codex review automation

Questa automazione coordina direttamente Claude Code e Codex CLI.
Le nuove patch vengono selezionate esclusivamente da `automation/roadmap.json`,
derivata dalla roadmap approvata in `docs/integration_phase1_report.md`.

## Protezioni

- Claude Code usa `--permission-mode auto --tools default`.
- Claude e Codex si passano direttamente il controllo senza attendere heartbeat
  o approvazioni intermedie.
- Dopo una patch approvata viene avviata soltanto la prima patch canonica
  `pending` con prerequisiti completati e `auto_run=true`.
- Se specifica o prerequisiti mancano, lo stato diventa `roadmap_blocked`;
  l'automazione non inventa nuove patch.
- Massimo tre cicli Claude.
- Claude non deve modificare `automation/`, avviare bot, usare API exchange,
  inviare Telegram, cancellare file, eseguire reset Git, commit o push.
- Codex esegue solo review e test; non corregge il codice prodotto durante il
  ciclo automatico.
- Ogni prompt, log e stato Git viene conservato.
- Un manifest SHA-256 prima/dopo identifica esattamente i file cambiati da ogni
  ciclo, anche quando erano gia modificati o non tracciati.
- Claude e Codex devono usare analisi ad alto segnale: file rilevanti, test mirati
  prima della suite completa, output sintetici e nessuna rilettura inutile.

## Comandi

Validare configurazione e CLI:

```powershell
.\automation\orchestrator.bat -Validate
```

Mostrare la prossima patch canonica senza modificare stato o avviare agenti:

```powershell
.\automation\orchestrator.bat -RoadmapPreview
```

Mostrare lo stato:

```powershell
.\automation\orchestrator.bat -Status
```

Monitorare live Claude e Codex:

```powershell
.\automation\monitor_live.bat
```

Il monitor mostra stato, processi, ultimi file modificati, stream operativo di
Claude e review Codex. Non espone il ragionamento interno degli agenti.

Mostrare la barriera quote:

```powershell
.\automation\orchestrator.bat -QuotaStatus
```

Registrare un limite e i due differenti orari di reset:

```powershell
.\automation\orchestrator.bat -QuotaLimited claude `
  -ClaudeResetAt "2026-06-08 18:00 +02:00" `
  -CodexResetAt "2026-06-08 19:30 +02:00"
```

Usare `-QuotaLimited codex` quando il limite riguarda Codex. Se gli orari non
sono specificati, viene applicata una pausa prudente di cinque ore a entrambi.
L'automazione riparte soltanto quando sono trascorsi entrambi gli orari.

Avviare il primo ciclo:

```powershell
.\automation\orchestrator.bat -Approve
```

Fermare:

```powershell
.\automation\orchestrator.bat -Stop
```

Lo script resta aperto e attende la review Codex. Se Codex respinge la patch,
scrive un nuovo `NEXT_CLAUDE_PROMPT.md` e avvia direttamente Claude.
Prima di avviare o riprendere Claude, lo script attende che eventuali altre
sessioni Claude Code siano state chiuse, evitando modifiche concorrenti.

## Stati principali

- `awaiting_claude_approval`: stato compatibile legacy; normalmente non usato.
- `claude_running`: Claude Code sta implementando la patch.
- `awaiting_codex_review`: Claude ha terminato e Codex deve verificare.
- `quota_waiting`: uno dei due ha raggiunto il limite; entrambi devono risultare
  resettati prima della ripresa.
- `approved`: review superata, automazione conclusa.
- `roadmap_complete`: tutte le patch canoniche automatiche sono completate.
- `roadmap_blocked`: nessuna patch canonica eleggibile o specifica insufficiente.
- `blocked`: limite cicli o errore non recuperabile.
- `stopped`: arresto richiesto dall'operatore.

L'heartbeat Codex rimane sospeso ed e usato soltanto come fallback se la CLI
diretta non e disponibile.

Se Claude raggiunge il limite, viene conservato il suo `session_id` e il ciclo
riprende con `--resume`, senza incrementare il contatore. Se Codex si interrompe,
lo stato della review resta conservato e il medesimo thread riprende dopo la
barriera quote. Un watchdog considera bloccata una review Codex rimasta in
esecuzione oltre il timeout configurato.
