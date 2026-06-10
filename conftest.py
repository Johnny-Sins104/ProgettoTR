"""Root conftest — makes pytest discover tests across the monorepo layout."""
import sys
from pathlib import Path

# Ensure trading_bot/ is importable in all tests regardless of cwd
_tb = Path(__file__).parent / "trading_bot"
if str(_tb) not in sys.path:
    sys.path.insert(0, str(_tb))
