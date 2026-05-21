"""
Modulo Walk-Forward (core/walk_forward.py)
Gestisce la scomposizione temporale rigorosa del dataset in fold di addestramento e test,
neutralizzando la sovrapposizione delle label e la correlazione seriale tramite purging ed embargoing.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Union
import pandas as pd
import numpy as np
from config import Config

@dataclass
class WalkForwardFold:
    """
    Rappresenta una singola scomposizione temporale (fold) walk-forward
    con isolamento statistico perfetto tramite embargo e predisposizione per il purging.
    """
    fold_idx: int
    train_start: int
    train_end: int
    embargo_start: int
    embargo_end: int
    test_start: int
    test_end: int
    
    # Timestamps corrispondenti
    train_start_time: Optional[pd.Timestamp] = None
    train_end_time: Optional[pd.Timestamp] = None
    embargo_start_time: Optional[pd.Timestamp] = None
    embargo_end_time: Optional[pd.Timestamp] = None
    test_start_time: Optional[pd.Timestamp] = None
    test_end_time: Optional[pd.Timestamp] = None
    
    # Metriche di diagnostica del fold
    num_purged_samples: int = 0
    effective_train_size: int = 0
    effective_test_size: int = 0

    def to_dict(self) -> Dict[str, Union[int, str, None]]:
        """Esporta il fold come dizionario per retrocompatibilità."""
        return {
            "fold_idx": self.fold_idx,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "embargo_start": self.embargo_start,
            "embargo_end": self.embargo_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_start_time": str(self.train_start_time) if self.train_start_time else None,
            "train_end_time": str(self.train_end_time) if self.train_end_time else None,
            "embargo_start_time": str(self.embargo_start_time) if self.embargo_start_time else None,
            "embargo_end_time": str(self.embargo_end_time) if self.embargo_end_time else None,
            "test_start_time": str(self.test_start_time) if self.test_start_time else None,
            "test_end_time": str(self.test_end_time) if self.test_end_time else None,
            "num_purged_samples": self.num_purged_samples,
            "effective_train_size": self.effective_train_size,
            "effective_test_size": self.effective_test_size
        }


class WalkForwardPipeline:
    @staticmethod
    def get_wf_splits(
        total_len: int, 
        N: int = 2000, 
        M: int = 500, 
        embargo_gap: int = 100,
        train_mode: str = "expanding",
        df: Optional[pd.DataFrame] = None
    ) -> List[WalkForwardFold]:
        """
        Genera gli indici e i metadati dei fold walk-forward temporali puri.
        Garantisce che:
        - Ciascun test window parta da un indice 'test_start' >= N.
        - L'embargo gap separi nettamente le due finestre per eliminare leak da correlazione seriale:
          embargo_start = train_end + 1
          embargo_end = test_start - 1
          train_end = test_start - 1 - embargo_gap
        - Se fornito un DataFrame con index di tipo DatetimeIndex, risolve automaticamente i timestamp.
        """
        splits = []
        if total_len < N:
            return splits
            
        fold_idx = 1
        for test_start in range(N, total_len, M):
            # Calcolo esatto dei limiti basato sull'embargo gap configurato
            train_end = test_start - 1 - embargo_gap
            if train_end < 20:  # Minimo tecnico per features rolling
                continue
                
            test_end = min(test_start + M - 1, total_len - 1)
            
            # Modalità di addestramento: expanding (ancorato a 0) o rolling (finestra scorrevole di ampiezza N)
            if train_mode == "rolling":
                train_start = max(0, train_end - N)
            else:
                train_start = 0
                
            embargo_start = train_end + 1
            embargo_end = test_start - 1
            
            # Risoluzione timestamp se disponibile il DataFrame
            train_start_time = None
            train_end_time = None
            embargo_start_time = None
            embargo_end_time = None
            test_start_time = None
            test_end_time = None
            
            if df is not None and isinstance(df.index, pd.DatetimeIndex):
                train_start_time = df.index[train_start]
                train_end_time = df.index[train_end]
                embargo_start_time = df.index[embargo_start]
                embargo_end_time = df.index[embargo_end]
                test_start_time = df.index[test_start]
                test_end_time = df.index[test_end]
                
            fold = WalkForwardFold(
                fold_idx=fold_idx,
                train_start=train_start,
                train_end=train_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                test_start=test_start,
                test_end=test_end,
                train_start_time=train_start_time,
                train_end_time=train_end_time,
                embargo_start_time=embargo_start_time,
                embargo_end_time=embargo_end_time,
                test_start_time=test_start_time,
                test_end_time=test_end_time,
                effective_test_size=(test_end - test_start + 1)
            )
            
            splits.append(fold)
            fold_idx += 1
            
        return splits

    @staticmethod
    def print_timeline(splits: List[WalkForwardFold], total_len: int):
        """
        Stampa una rappresentazione visiva ASCII premium della scomposizione walk-forward.
        """
        if not splits:
            print("⚠️ Nessun split walk-forward da visualizzare.")
            return
            
        print("\n" + "=" * 80)
        print(" 📅 TIMELINE DEL PIPELINE DI VALIDAZIONE WALK-FORWARD (PURGED + EMBARGO)")
        print("=" * 80)
        
        bar_len = 40
        for fold in splits:
            # Calcolo dei blocchi proporzionali per la timeline
            t_start_ratio = int((fold.train_start / total_len) * bar_len)
            t_end_ratio = int((fold.train_end / total_len) * bar_len)
            emb_start_ratio = int((fold.embargo_start / total_len) * bar_len)
            emb_end_ratio = int((fold.embargo_end / total_len) * bar_len)
            test_start_ratio = int((fold.test_start / total_len) * bar_len)
            test_end_ratio = int((fold.test_end / total_len) * bar_len)
            
            line = ["."] * bar_len
            
            # Riempiamo la timeline
            for i in range(t_start_ratio, min(t_end_ratio + 1, bar_len)):
                line[i] = "T"  # Training
            for i in range(max(t_end_ratio + 1, emb_start_ratio), min(emb_end_ratio + 1, bar_len)):
                line[i] = "E"  # Embargo
            for i in range(max(emb_end_ratio + 1, test_start_ratio), min(test_end_ratio + 1, bar_len)):
                line[i] = "V"  # Validation / Test
                
            timeline_str = "".join(line)
            dates_str = ""
            if fold.train_start_time is not None and fold.test_end_time is not None:
                d1 = fold.train_start_time.strftime("%y-%m-%d")
                d2 = fold.test_end_time.strftime("%y-%m-%d")
                dates_str = f" ({d1} a {d2})"
                
            print(f"  Fold {fold.fold_idx:02d}: |{timeline_str}| {fold.train_start} -> {fold.test_end}{dates_str}")
            
        print("\n  Legenda: [T] = Train Window | [E] = Embargo Period (Gap) | [V] = Out-of-Sample Test")
        print("=" * 80 + "\n")
