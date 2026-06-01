"""
core/ai_engine.py — Backward-compatible wrapper for the MetaLabelingEngine
=============================================================================
Routes all legacy AI requests to the new institutional-grade MetaLabelingEngine
implementing the formal Stage 2 Lopez de Prado Meta-Labeling architecture.
"""

import os
from config import Config
from core.meta_labeling import MetaLabelingEngine, FEATURE_NAMES, XGBOOST_AVAILABLE, CALIBRATION_AVAILABLE

class TradingAI(MetaLabelingEngine):
    """
    Backward-compatible wrapper subclass of MetaLabelingEngine.
    Provides identical interface, singleton behavior, and retrain logic.
    """
    
    def retrain_if_needed(self, csv_path: str = None):
        """
        Auto-retrains the AI if the sample count in Parquet features grows.
        """
        if csv_path is None:
            csv_path = self.features_path
            
        if not os.path.exists(csv_path):
            return
            
        try:
            import polars as pl
            lines = pl.scan_parquet(csv_path).select(pl.len()).collect().item()
                
            last = int(getattr(self, "_last_auto_retrain_samples", 0) or 0)
            retrain_every = max(1, int(getattr(Config, "AI_RETRAIN_EVERY", 500) or 500))
            if lines >= Config.AI_MIN_SAMPLES and (last <= 0 or lines - last >= retrain_every):
                print(f"♻️ Riaddestramento automatico AI avviato (Campioni: {lines}, ultimo={last})...")
                self.train(csv_path)
                self._last_auto_retrain_samples = int(lines)
        except Exception:
            pass
