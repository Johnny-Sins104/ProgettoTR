"""test_integrity_audit_funding.py — Funding-series checks in the integrity audit.

Builds tiny parquet files in tmp_path and exercises _check_funding_file and
the funding routing/gate logic of run_market_data_integrity_audit.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_PATH = PROJECT_ROOT / "trading_bot" / "run_market_data_integrity_audit.py"

spec = importlib.util.spec_from_file_location("integrity_audit_module", _AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
sys.modules["integrity_audit_module"] = audit
spec.loader.exec_module(audit)


def _funding_df(
    n: int = 100,
    rate: float = 0.0001,
    freq: str = "8h",
    symbol: str = "BTC/USDT",
) -> pd.DataFrame:
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC"),
        "symbol": [symbol] * n,
        "funding_rate": [rate] * n,
    })


def _write(tmp_path: Path, df: pd.DataFrame, name: str = "btcusdt_funding.parquet") -> Path:
    path = tmp_path / name
    df.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# _check_funding_file
# ---------------------------------------------------------------------------

def test_clean_funding_file_approved(tmp_path: Path) -> None:
    path = _write(tmp_path, _funding_df())
    result = audit._check_funding_file(path)
    assert result["approved"] is True
    assert result["rejection_reason"] is None
    assert result["kind"] == "funding"
    assert result["rows"] == 100
    assert result["modal_interval_hours"] == 8.0
    assert result["gap_count"] == 0


def test_4h_grid_approved(tmp_path: Path) -> None:
    """4h settlement interval is allowlisted (some USDT-M symbols use it)."""
    path = _write(tmp_path, _funding_df(freq="4h"))
    result = audit._check_funding_file(path)
    assert result["approved"] is True
    assert result["modal_interval_hours"] == 4.0


def test_gap_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df = df.drop(index=[50, 51]).reset_index(drop=True)  # 24h hole in an 8h grid
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "gap" in result["rejection_reason"]
    assert result["gap_count"] == 1


def test_null_rate_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df.loc[10, "funding_rate"] = None
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "null" in result["rejection_reason"]


def test_off_grid_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df["datetime"] = df["datetime"].astype(object)
    df.loc[10, "datetime"] = df.loc[10, "datetime"] + pd.Timedelta(minutes=13)
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "off-grid" in result["rejection_reason"]


def test_unsupported_grid_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, _funding_df(freq="3h"))
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "allowlist" in result["rejection_reason"]


def test_rate_cap_breach_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df.loc[10, "funding_rate"] = 0.0080
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "0.0075" in result["rejection_reason"]
    assert result["rate_cap_violations"] == 1


def test_wrong_symbol_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df.loc[10, "symbol"] = "ETH/USDT"
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "symbol" in result["rejection_reason"]
    assert result["symbol_mismatch_count"] == 1


def test_duplicate_timestamps_rejected(tmp_path: Path) -> None:
    df = _funding_df()
    df["datetime"] = df["datetime"].astype(object)
    df.loc[11, "datetime"] = df.loc[10, "datetime"]
    df = df.sort_values("datetime").reset_index(drop=True)
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "duplicate" in result["rejection_reason"]


def test_missing_columns_rejected(tmp_path: Path) -> None:
    df = _funding_df().drop(columns=["funding_rate"])
    path = _write(tmp_path, df)
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "missing columns" in result["rejection_reason"]


def test_empty_file_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, _funding_df().iloc[0:0])
    result = audit._check_funding_file(path)
    assert result["approved"] is False
    assert "empty" in result["rejection_reason"]


# ---------------------------------------------------------------------------
# Routing and gate folding
# ---------------------------------------------------------------------------

def test_funding_pattern_routes_only_funding_files() -> None:
    """OHLCV cache names are unaffected by the funding routing pattern."""
    assert audit._FUNDING_FILE_PATTERN.search("btcusdt_funding.parquet")
    assert audit._FUNDING_FILE_PATTERN.search("ETHUSDT_FUNDING.parquet")
    for ohlcv_name in (
        "btc_5m_150k_cache.parquet",
        "btcusdt_4h_cache.parquet",
        "xrpusdt_1d_cache.parquet",
        "market_features.parquet",
    ):
        assert not audit._FUNDING_FILE_PATTERN.search(ohlcv_name), ohlcv_name


def test_1d_timeframe_inferred() -> None:
    assert audit._infer_timeframe("btcusdt_1d_cache.parquet") == "1d"
    assert audit._TF_MINUTES["1d"] == 1440


def test_funding_rejection_folds_into_raw_data_gate() -> None:
    gates = audit._evaluate_gates(
        inventory=[],
        contamination={"signal_density_groups": [], "other_contaminated_reports": []},
        timeframe_contamination={"5m_is_copy_of": "UNKNOWN", "15m_is_copy_of": "UNKNOWN"},
        missing_15m=[],
        agg_check={"status": "PASS"},
        la_check={"status": "PASS"},
        funding_inventory=[
            {"file": "btcusdt_funding.parquet", "approved": False,
             "rejection_reason": "3 funding interval gaps"},
        ],
    )
    assert gates["raw_data_gate"] == "BLOCKED"
    assert any("funding" in r for r in gates["raw_data_gate_reasons"])


def test_no_funding_files_is_not_a_failure() -> None:
    """Absence of funding series must not block any gate."""
    gates = audit._evaluate_gates(
        inventory=[],
        contamination={"signal_density_groups": [], "other_contaminated_reports": []},
        timeframe_contamination={"5m_is_copy_of": "UNKNOWN", "15m_is_copy_of": "UNKNOWN"},
        missing_15m=[],
        agg_check={"status": "PASS"},
        la_check={"status": "PASS"},
        funding_inventory=[],
    )
    assert gates["raw_data_gate"] == "PASS"


def test_approved_funding_keeps_gate_pass() -> None:
    gates = audit._evaluate_gates(
        inventory=[],
        contamination={"signal_density_groups": [], "other_contaminated_reports": []},
        timeframe_contamination={"5m_is_copy_of": "UNKNOWN", "15m_is_copy_of": "UNKNOWN"},
        missing_15m=[],
        agg_check={"status": "PASS"},
        la_check={"status": "PASS"},
        funding_inventory=[
            {"file": "btcusdt_funding.parquet", "approved": True, "rejection_reason": None},
        ],
    )
    assert gates["raw_data_gate"] == "PASS"
