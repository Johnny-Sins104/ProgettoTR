Esegui una review indipendente e ad alto segnale della patch Claude appena terminata.

Leggi soltanto:
- `automation/CLAUDE_DONE.json`;
- il prompt archiviato indicato nel file;
- il manifest `changed_files`;
- il report della patch, se presente;
- i file realmente modificati e le dipendenze strettamente necessarie.

Regole:
- non fidarti del report o dei test di Claude;
- verifica i requisiti e riproduci i casi critici;
- esegui prima test mirati;
- esegui `python -m pytest -q` una sola volta, soltanto se i mirati passano;
- non modificare alcun file;
- non avviare bot, API exchange o Telegram;
- non fare reset, commit o push;
- minimizza token, letture e output.

Decisione:
- `approved`: tutti i requisiti verificati e suite valida;
- `fix_required`: problemi riprodotti e correggibili in un altro ciclo;
- `blocked`: review non completabile o limite cicli.

In `review_markdown` inserisci esito, soli problemi verificati, test e prossimo passo.
In `next_claude_prompt` inserisci esclusivamente i fix verificati; lascialo vuoto se approvato o bloccato.
