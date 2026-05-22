from pathlib import Path
from types import SimpleNamespace

from core.historical_cache import cache_filename, discover_local_caches, timeframe_to_minutes


def test_timeframe_to_minutes():
    assert timeframe_to_minutes("15m") == 15
    assert timeframe_to_minutes("1h") == 60


def test_cache_filename_btc_compatibility():
    assert cache_filename("BTC/USDT", "15m", 50000) == "btc_15m_50k_cache.parquet"


def test_discover_local_caches_empty(tmp_path: Path):
    assert discover_local_caches(tmp_path, "BTC/USDT", "15m") == []
