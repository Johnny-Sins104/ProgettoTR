# PROMPT 29.4.4u-39 — Generic LSR-v2 supervised paper postmortem execution scaffold

Patch scaffold-only/read-only/fail-closed. Consuma il report `29.4.4u-38` e modella il gate futuro di esecuzione postmortem paper-only.

## Garanzie

- Nessun postmortem reale.
- Nessuna mutazione di `paper_state` o `paper_status`.
- Nessun submit/close.
- Nessuna chiamata broker.
- Nessun invio Telegram/network.
- Nessun avvio scheduler.
- Nessun live/testnet/exchange.
- Nessuna espansione ordinale.

## Output atteso

`LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD_READY` con `generic_postmortem_execution_allowed=false`, `paper_postmortem_ready=false`, `would_run_postmortem=false`, `would_mutate_paper_state=false`, `would_mutate_paper_status=false`, `would_send_telegram=false` e `would_start_scheduler=false`.
