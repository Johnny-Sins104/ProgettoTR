"""
core/optimizer.py — FeedbackLoop: registra trade e ottimizza i pesi del DecisionEngine.

Flusso:
  1. record_trade(outcome, active_confirmations)  →  scrive su data/trade_memory.json
  2. optimize_weights(current_weights)             →  legge gli ultimi 20 trade,
                                                      calcola il Win Rate per ogni
                                                      conferma e ritorna i pesi aggiornati.
"""
import json
from pathlib import Path

# ── Costanti ────────────────────────────────────────────────────────────── #
MEMORY_FILE    = Path("data/trade_memory.json")
WINDOW_SIZE    = 20       # ultimi N trade su cui calcolare il Win Rate
ADJUST_RATE    = 0.10     # variazione peso: ±10%
WIN_RATE_LOW   = 0.40     # sotto questa soglia → penalizza
WIN_RATE_HIGH  = 0.60     # sopra questa soglia → premia
WEIGHT_MIN     = 5        # peso minimo consentito (evita azzeramento)
# ────────────────────────────────────────────────────────────────────────── #


class FeedbackLoop:
    """Memorizza i risultati dei trade e ottimizza i pesi della strategia."""

    def __init__(self, memory_path: Path | str = MEMORY_FILE) -> None:
        self.memory_path = Path(memory_path)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    # ── I/O ─────────────────────────────────────────────────────────────── #

    def _load(self) -> list[dict]:
        if not self.memory_path.exists():
            return []
        with open(self.memory_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, records: list[dict]) -> None:
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    # ── API pubblica ─────────────────────────────────────────────────────── #

    def record_trade(
        self,
        outcome: str,                          # "WIN" | "LOSS"
        active_confirmations: dict[str, bool], # es. {"engulfing": True, "support": False}
    ) -> None:
        """Aggiunge un record al file di memoria."""
        records = self._load()
        records.append({
            "outcome":       outcome,
            "confirmations": active_confirmations,
        })
        self._save(records)

    def optimize_weights(self, current_weights: dict[str, int]) -> dict[str, int]:
        """
        Legge gli ultimi WINDOW_SIZE trade e aggiusta ogni peso in base al
        Win Rate della conferma associata:
          - Win Rate < WIN_RATE_LOW  → peso * (1 - ADJUST_RATE)
          - Win Rate > WIN_RATE_HIGH → peso * (1 + ADJUST_RATE)
          - altrimenti               → invariato
        Ritorna sempre un dict con gli stessi tasti di current_weights.
        """
        records = self._load()
        window  = records[-WINDOW_SIZE:]

        # Dati insufficienti → ritorna i pesi correnti senza toccare nulla
        if len(window) < 5:
            print(f"[OPTIMIZER] Dati insufficienti ({len(window)} trade). Pesi invariati.")
            return current_weights.copy()

        new_weights: dict[str, int] = {}

        for key, w in current_weights.items():
            trades_with_key = [
                t for t in window
                if t["confirmations"].get(key, False)
            ]

            if not trades_with_key:
                new_weights[key] = w   # conferma mai attivata → invariato
                continue

            wins     = sum(1 for t in trades_with_key if t["outcome"] == "WIN")
            win_rate = wins / len(trades_with_key)

            if win_rate < WIN_RATE_LOW:
                new_w = max(WEIGHT_MIN, int(w * (1 - ADJUST_RATE)))
                tag   = f"↓ WR={win_rate:.0%} → penalizzato"
            elif win_rate > WIN_RATE_HIGH:
                new_w = int(w * (1 + ADJUST_RATE))
                tag   = f"↑ WR={win_rate:.0%} → premiato"
            else:
                new_w = w
                tag   = f"~ WR={win_rate:.0%} → invariato"

            new_weights[key] = new_w
            print(f"[OPTIMIZER] {key:<12} {w:>3} → {new_w:>3}  ({tag})")

        return new_weights
