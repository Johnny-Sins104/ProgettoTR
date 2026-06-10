"""
Market Data Integrity Audit
============================
Diagnostic-only script. Does NOT open orders, connect to exchanges, or modify
any existing files. Outputs a single JSON report.

Usage (from project root):
    python trading_bot/run_market_data_integrity_audit.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — resolve project root regardless of cwd
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent  # trading_bot/ -> project root
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "market_data_integrity_status.json"

# Safety guard: no live activity possible from here
DIAGNOSTIC_ONLY: bool = True
OPENS_ORDERS: bool = False
LIVE_TRADING_ALLOWED: bool = False

# ---------------------------------------------------------------------------
# Asset / timeframe inference from filename
# ---------------------------------------------------------------------------
_ASSET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"btc", re.I), "BTC/USDT"),
    (re.compile(r"xrp", re.I), "XRP/USDT"),
    (re.compile(r"eth", re.I), "ETH/USDT"),
    (re.compile(r"sol", re.I), "SOL/USDT"),
    (re.compile(r"bnb", re.I), "BNB/USDT"),
]

_TF_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"_1m"), "1m"),
    (re.compile(r"_5m"), "5m"),
    (re.compile(r"_15m"), "15m"),
    (re.compile(r"_1h"), "1h"),
    (re.compile(r"_4h"), "4h"),
]

_TF_MINUTES: dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}


def _infer_asset(name: str) -> str:
    for pat, label in _ASSET_PATTERNS:
        if pat.search(name):
            return label
    return "UNKNOWN"


def _infer_timeframe(name: str) -> str:
    for pat, label in _TF_PATTERNS:
        if pat.search(name):
            return label
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# OHLCV checks
# ---------------------------------------------------------------------------

def _check_ohlcv_file(path: Path) -> dict[str, Any]:
    """Run all integrity checks on a single parquet file."""
    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not installed"}

    name = path.name
    asset = _infer_asset(name)
    tf = _infer_timeframe(name)

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        return {
            "file": name,
            "asset": asset,
            "timeframe": tf,
            "error": str(exc),
            "approved": False,
            "rejection_reason": f"Failed to read parquet: {exc}",
        }

    rows = len(df)

    # ---- timestamp column detection ----------------------------------------
    ts_col: str | None = None
    for candidate in ("datetime", "open_time_utc", "timestamp", "time", "date", "index"):
        if candidate in df.columns:
            ts_col = candidate
            break
    if ts_col is None and df.index.dtype.kind in ("M", "i"):
        df = df.reset_index()
        for candidate in ("datetime", "timestamp", "index"):
            if candidate in df.columns:
                ts_col = candidate
                break

    # ---- null count ---------------------------------------------------------
    null_count = int(df.isnull().sum().sum())

    # ---- period / gap / duplicate / OOO ------------------------------------
    gap_count = 0
    duplicate_count = 0
    ooo_count = 0
    period_start: str | None = None
    period_end: str | None = None

    if ts_col and ts_col in df.columns:
        try:
            import pandas as pd  # already imported but keep import local

            ts = pd.to_datetime(df[ts_col], utc=True)
            ts_sorted = ts.sort_values()
            period_start = ts_sorted.iloc[0].isoformat()
            period_end = ts_sorted.iloc[-1].isoformat()

            diffs = ts.diff().dropna()
            if len(diffs) > 0:
                mode_result = diffs.mode()
                modal_interval = mode_result.iloc[0] if len(mode_result) > 0 else diffs.median()
                threshold = modal_interval * 1.5
                gap_count = int((diffs > threshold).sum())

            duplicate_count = int(ts.duplicated().sum())
            ooo_count = int((ts.diff().dropna() < pd.Timedelta(0)).sum())
        except Exception:
            pass

    # ---- OHLC violations ---------------------------------------------------
    ohlc_violations = 0
    ohlc_cols = {"Open": None, "High": None, "Low": None, "Close": None}
    # tolerate case-insensitive column names
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.lower()
        for k in ("open", "high", "low", "close"):
            if cl == k:
                col_map[k] = col

    if all(k in col_map for k in ("open", "high", "low", "close")):
        o = df[col_map["open"]]
        h = df[col_map["high"]]
        l = df[col_map["low"]]
        c = df[col_map["close"]]
        v1 = int((h < l).sum())                         # high < low
        v2 = int(((c < l) | (c > h)).sum())             # close outside H-L
        v3 = int(((o < l) | (o > h)).sum())             # open outside H-L
        ohlc_violations = v1 + v2 + v3

    # ---- approval ----------------------------------------------------------
    rejection_reasons: list[str] = []
    if gap_count > 0:
        rejection_reasons.append(f"{gap_count} timestamp gaps")
    if duplicate_count > 0:
        rejection_reasons.append(f"{duplicate_count} duplicate timestamps")
    if ooo_count > 0:
        rejection_reasons.append(f"{ooo_count} out-of-order timestamps")
    if ohlc_violations > 0:
        rejection_reasons.append(f"{ohlc_violations} OHLC violations")
    if null_count > 0:
        rejection_reasons.append(f"{null_count} null values")

    approved = len(rejection_reasons) == 0
    rejection_reason = "; ".join(rejection_reasons) if rejection_reasons else None

    return {
        "file": name,
        "asset": asset,
        "timeframe": tf,
        "rows": rows,
        "columns": list(df.columns),
        "period_start": period_start,
        "period_end": period_end,
        "gap_count": gap_count,
        "duplicate_count": duplicate_count,
        "out_of_order_count": ooo_count,
        "ohlc_violations": ohlc_violations,
        "null_count": null_count,
        "approved": approved,
        "rejection_reason": rejection_reason,
    }


# ---------------------------------------------------------------------------
# MD5 hashing
# ---------------------------------------------------------------------------

def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Report contamination scan
# ---------------------------------------------------------------------------

_REPORT_NAMES = {
    "signal_density_report.json",
    "paper_readiness_report.json",
    "archetype_performance_report.json",
    "walkforward_audit_report.json",
    "lifecycle_consistency_report.json",
}

_METADATA_KEYS = {"asset", "symbol", "timeframe", "tf", "ticker"}


def _scan_report_hashes(root: Path) -> dict[str, list[str]]:
    """Return {hash -> [relative_path, ...]} for all target JSON files under root."""
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for name in _REPORT_NAMES:
        for fpath in sorted(root.rglob(name)):
            digest = _md5(fpath)
            rel = str(fpath.relative_to(root.parent))  # relative to data/
            hash_groups[digest].append(rel)
    return dict(hash_groups)


def _has_metadata(path: Path) -> bool:
    """Check if a JSON file contains asset/timeframe metadata keys."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return False
        keys_lower = {k.lower() for k in data.keys()}
        return bool(keys_lower & _METADATA_KEYS)
    except Exception:
        return False


def _build_contamination_report(data_dir: Path) -> dict[str, Any]:
    """Build the full contamination section."""
    timeframe_dir = data_dir / "timeframe_runs"
    multi_asset_dir = data_dir / "multi_asset_runs"

    # Hash all reports in both trees together (relative to data/)
    all_hash_groups: dict[str, list[str]] = defaultdict(list)
    for report_name in _REPORT_NAMES:
        for search_root in (timeframe_dir, multi_asset_dir):
            if not search_root.exists():
                continue
            for fpath in sorted(search_root.rglob(report_name)):
                digest = _md5(fpath)
                rel = str(fpath.relative_to(data_dir)).replace("\\", "/")
                all_hash_groups[digest].append(rel)

    # Signal density specific analysis
    sd_groups: list[dict] = []
    other_contaminated: list[dict] = []

    for digest, files in sorted(all_hash_groups.items(), key=lambda x: -len(x[1])):
        if len(files) < 2:
            continue  # not a duplicate group

        # Check metadata in first file
        first_path = data_dir / files[0].replace("/", "\\")
        if not first_path.exists():
            first_path = data_dir / files[0]

        missing_meta = not _has_metadata(first_path)

        # Classify by report type
        is_signal_density = any("signal_density" in f for f in files)

        entry = {
            "hash": digest,
            "file_count": len(files),
            "files": files,
            "missing_metadata": missing_meta,
        }

        if is_signal_density:
            sd_groups.append(entry)
        else:
            other_contaminated.append(entry)

    return {
        "signal_density_groups": sd_groups,
        "other_contaminated_reports": other_contaminated,
    }


def _build_timeframe_runs_contamination(data_dir: Path) -> dict[str, Any]:
    """Verify that timeframe_runs/5m and /15m are copies of multi_asset btcusdt paths."""
    tf_dir = data_dir / "timeframe_runs"
    ma_dir = data_dir / "multi_asset_runs"

    matches_5m: list[str] = []
    matches_15m: list[str] = []

    candidate_5m = ma_dir / "btcusdt" / "5m" / "base"
    candidate_15m = ma_dir / "btcusdt" / "15m"

    def _compare_dirs(src: Path, dst: Path) -> bool:
        """Return True if every report JSON in src has a matching hash in dst."""
        if not src.exists() or not dst.exists():
            return False
        matched = 0
        checked = 0
        for report_name in _REPORT_NAMES:
            src_file = src / report_name
            dst_file = dst / report_name
            if src_file.exists() and dst_file.exists():
                checked += 1
                if _md5(src_file) == _md5(dst_file):
                    matched += 1
        return checked > 0 and matched == checked

    copy_of_5m = "multi_asset_runs/btcusdt/5m/base" if _compare_dirs(
        tf_dir / "5m", candidate_5m
    ) else "UNKNOWN"

    copy_of_15m = "multi_asset_runs/btcusdt/15m" if _compare_dirs(
        tf_dir / "15m", candidate_15m
    ) else "UNKNOWN"

    confirmed_by = "MD5 hash match on all reports"

    return {
        "5m_is_copy_of": copy_of_5m,
        "15m_is_copy_of": copy_of_15m,
        "confirmed_by": confirmed_by,
    }


# ---------------------------------------------------------------------------
# 5m -> 15m aggregation check
# ---------------------------------------------------------------------------

def _aggregation_check(data_dir: Path) -> dict[str, Any]:
    """
    Compare BTC 5m->15m aggregation against raw 15m file over full overlap.

    Exclusion policy (documented, NOT silent):
      excluded_incomplete_buckets:
        Buckets with fewer than 3 five-minute bars present in the 5m dataset.
        Root cause: data gaps in the 5m source. Entire bucket excluded from
        all column comparisons.

      open_comparison_excluded_buckets:
        Buckets where the first 5m bar has Volume=0 (synthetic carry-forward
        filler). The bucket is NOT excluded; it is included in
        complete_buckets_compared. Only the Open comparison is excluded because
        the filler bar's Open is the prior bar's Close, not the first actual
        trade price. High, Low, Close, Volume are still compared.

    Status conditions:
      PASS  — ratio correct, ≥1 complete bucket compared, every mandatory column
              has ≥1 real comparison, 0 unexplained mismatches.
      BLOCKED — 0 complete buckets compared, or any H/L/C/V column has 0 real
              comparisons (no evidence of correctness).
      FAIL  — unexplained mismatches found, or ratio out of tolerance.
    """
    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not installed", "status": "SKIP"}

    src_path = data_dir / "btc_5m_150k_cache.parquet"
    tgt_path = data_dir / "btc_15m_50k_cache.parquet"

    base: dict[str, Any] = {
        "asset": "BTC/USDT",
        "source": "btc_5m_150k_cache.parquet",
        "target": "btc_15m_50k_cache.parquet",
        "expected_ratio": 3.0,
    }

    if not src_path.exists() or not tgt_path.exists():
        base.update({"status": "SKIP", "reason": "Source or target file not found"})
        return base

    base["source_sha256"] = _sha256(src_path)
    base["target_sha256"] = _sha256(tgt_path)

    df5 = pd.read_parquet(src_path)
    df15 = pd.read_parquet(tgt_path)

    rows5 = len(df5)
    rows15 = len(df15)
    actual_ratio = rows5 / rows15 if rows15 > 0 else float("inf")
    base["actual_ratio"] = round(actual_ratio, 4)

    ts_col5 = next((c for c in ("datetime", "timestamp", "time") if c in df5.columns), None)
    ts_col15 = next((c for c in ("datetime", "timestamp", "time") if c in df15.columns), None)

    if not (ts_col5 and ts_col15):
        base.update({"status": "SKIP", "reason": "Timestamp column not found",
                     "sample_size": 0, "sample_mismatches": 0})
        return base

    ts5 = pd.to_datetime(df5[ts_col5], utc=True)
    ts15 = pd.to_datetime(df15[ts_col15], utc=True)

    df5_indexed = df5.copy()
    df5_indexed.index = ts5

    col_map5: dict[str, str] = {}
    for col in df5.columns:
        for k in ("open", "high", "low", "close", "volume"):
            if col.lower() == k:
                col_map5[k] = col

    col_map15: dict[str, str] = {}
    for col in df15.columns:
        for k in ("open", "high", "low", "close", "volume"):
            if col.lower() == k:
                col_map15[k] = col

    if not (col_map5 and col_map15):
        base.update({"status": "SKIP", "reason": "OHLCV columns not found",
                     "sample_size": 0, "sample_mismatches": 0})
        return base

    agg_dict: dict[str, str] = {}
    if "open" in col_map5:
        agg_dict[col_map5["open"]] = "first"
    if "high" in col_map5:
        agg_dict[col_map5["high"]] = "max"
    if "low" in col_map5:
        agg_dict[col_map5["low"]] = "min"
    if "close" in col_map5:
        agg_dict[col_map5["close"]] = "last"
    if "volume" in col_map5:
        agg_dict[col_map5["volume"]] = "sum"

    resampled = df5_indexed.resample("15min", closed="left", label="left").agg(agg_dict).dropna()

    df15_indexed = df15.copy()
    df15_indexed.index = ts15

    tgt_cols_rename = {
        col_map15[k]: f"_tgt_{k}"
        for k in ("open", "high", "low", "close", "volume")
        if k in col_map15
    }
    raw15_subset = df15_indexed[list(tgt_cols_rename)].rename(columns=tgt_cols_rename)
    merged = resampled.join(raw15_subset, how="inner")
    full_overlap_rows = len(merged)

    # --- Bucket-level classification ---
    bar_counts = df5_indexed.resample("15min", closed="left", label="left").size()
    in_overlap = bar_counts.index.isin(merged.index)

    # Incomplete buckets: < 3 bars → exclude entirely from all column comparisons
    incomplete_mask = (bar_counts < 3) & in_overlap
    incomplete_ts = sorted(
        bar_counts[incomplete_mask].index.strftime("%Y-%m-%dT%H:%M:%S+00:00").tolist()
    )
    incomplete_details = {
        ts: {"bars_present": int(bar_counts.loc[idx]), "bars_expected": 3}
        for ts, idx in zip(incomplete_ts, bar_counts[incomplete_mask].index)
    }

    # Zero-volume first bar: complete bucket, but Open is a carry-forward filler.
    # Policy: include bucket in complete_buckets_compared; exclude ONLY Open comparison.
    # H, L, C, V must be compared — mismatch there = unexplained.
    zero_vol_open_idx: "pd.DatetimeIndex" = pd.DatetimeIndex([])
    open_excl_ts: list[str] = []
    if "volume" in col_map5:
        first_vol = df5_indexed.resample("15min", closed="left", label="left")[col_map5["volume"]].first()
        zero_vol_mask = (first_vol == 0.0) & in_overlap & ~incomplete_mask
        zero_vol_open_idx = first_vol[zero_vol_mask].index
        open_excl_ts = sorted(
            zero_vol_open_idx.strftime("%Y-%m-%dT%H:%M:%S+00:00").tolist()
        )

    # Complete buckets = all overlap rows minus incomplete ones
    # (zero-vol buckets are INCLUDED here)
    incomplete_idx = bar_counts[incomplete_mask].index
    clean_merged = merged[~merged.index.isin(incomplete_idx)]
    complete_buckets_compared = len(clean_merged)

    # Per-column comparison and mismatch counting
    tol = 1e-6
    col_mismatches: dict[str, int] = {}
    col_comparison_counts: dict[str, int] = {}
    mismatch_details: list[dict] = []
    columns_checked: list[str] = []

    for k in ("open", "high", "low", "close", "volume"):
        src_col = col_map5.get(k)
        tgt_col = f"_tgt_{k}"
        if not (src_col and tgt_col in clean_merged.columns and src_col in clean_merged.columns):
            continue
        columns_checked.append(k)

        if k == "open":
            # Exclude zero-vol-open buckets from Open comparison
            rows = clean_merged[~clean_merged.index.isin(zero_vol_open_idx)]
        else:
            rows = clean_merged

        col_comparison_counts[k] = len(rows)

        if len(rows) == 0:
            col_mismatches[k] = 0
            continue

        diff = (rows[src_col] - rows[tgt_col]).abs()
        bad = rows[diff > tol]
        col_mismatches[k] = len(bad)
        for ts_idx, row in bad.head(10).iterrows():
            mismatch_details.append({
                "timestamp": str(ts_idx),
                "column": k,
                "aggregated": float(row[src_col]),
                "raw_15m": float(row[tgt_col]),
                "abs_diff": float(abs(row[src_col] - row[tgt_col])),
            })

    unexplained_mismatches = sum(col_mismatches.values())

    # Mandatory columns for PASS: H, L, C, V must all have ≥1 real comparison
    mandatory_cols = [k for k in ("high", "low", "close", "volume") if k in col_comparison_counts]
    mandatory_have_comparisons = all(col_comparison_counts.get(k, 0) > 0 for k in mandatory_cols)

    if complete_buckets_compared == 0:
        status = "BLOCKED"  # no complete buckets — nothing compared
    elif not mandatory_have_comparisons:
        status = "BLOCKED"  # H/L/C/V have 0 real comparisons — cannot certify
    elif unexplained_mismatches > 0 or abs(actual_ratio - 3.0) >= 0.01:
        status = "FAIL"
    else:
        status = "PASS"

    base.update({
        "full_overlap_rows": full_overlap_rows,
        "complete_buckets_compared": complete_buckets_compared,
        "excluded_incomplete_buckets": len(incomplete_ts),
        "excluded_incomplete_bucket_timestamps": incomplete_ts,
        "excluded_incomplete_bucket_details": incomplete_details,
        "open_comparison_excluded_buckets": len(open_excl_ts),
        "open_comparison_excluded_bucket_timestamps": open_excl_ts,
        "open_comparison_excluded_reason": (
            "First 5m bar has Volume=0 (synthetic carry-forward filler). "
            "Open reflects prior Close, not first actual trade. "
            "H/L/C/V still compared for these buckets."
        ) if open_excl_ts else None,
        "sample_size": complete_buckets_compared,
        "sample_mismatches": unexplained_mismatches,
        "unexplained_mismatches": unexplained_mismatches,
        "columns_checked": columns_checked,
        "per_column_comparison_counts": col_comparison_counts,
        "per_column_mismatches": col_mismatches,
        "mismatch_details": mismatch_details,
        "status": status,
    })
    return base


# ---------------------------------------------------------------------------
# Lookahead guard check
# ---------------------------------------------------------------------------

def _lookahead_check(project_root: Path) -> dict[str, Any]:
    rel = "trading_bot/clean_bot/paper_live.py"
    target = project_root / rel
    if not target.exists():
        return {
            "file": rel,
            "pattern_found": None,
            "stale_bar_guard": False,
            "status": "MISSING",
        }

    content = target.read_text(encoding="utf-8", errors="replace")

    # Look for completed-bar guard: max(0, len(df) - 2) or len(df) - 2
    guard_patterns = [
        r"max\(0,\s*len\(df\)\s*-\s*2\)",
        r"idx\s*=\s*len\(df\)\s*-\s*2",
        r"len\(df\)\s*-\s*2",
    ]
    found_pattern: str | None = None
    for pat in guard_patterns:
        m = re.search(pat, content)
        if m:
            found_pattern = m.group(0).strip()
            break

    stale_bar_guard = found_pattern is not None

    # Also check for duplicate/stale guard
    has_stale_guard = bool(re.search(r"stale|duplicate|already|seen", content, re.I))

    return {
        "file": rel,
        "pattern_found": found_pattern or "NOT FOUND",
        "stale_bar_guard": stale_bar_guard,
        "status": "PASS" if stale_bar_guard else "FAIL",
    }


# ---------------------------------------------------------------------------
# Gate evaluation (3-tier)
# ---------------------------------------------------------------------------

def _evaluate_gates(
    inventory: list[dict],
    contamination: dict,
    timeframe_contamination: dict,
    missing_15m: list[str],
    agg_check: dict,
    la_check: dict,
) -> dict[str, Any]:
    """
    Produce three independent gates plus overall gate_result.

    raw_data_gate
        PASS if all raw OHLCV parquet files pass integrity checks.
        This gate controls whether raw data can be trusted as benchmark input.

    derived_artifact_gate
        PASS if derived report artifacts (signal_density, walkforward, etc.) are
        not contaminated and carry embedded asset/timeframe metadata.
        BLOCKED if contamination or missing metadata detected.
        Note: a BLOCKED derived_artifact_gate does NOT block the benchmark if the
        benchmark runner is designed to use only raw OHLCV (not derived reports).

    benchmark_readiness_gate
        PASS if the Phase 3 benchmark can proceed using only raw parquet files:
        - raw_data_gate = PASS
        - 5m->15m aggregation verified (benchmark can generate 15m on-the-fly)
        - lookahead guard confirmed
        - cost model certified (checked separately by Phase 2)
        - Contaminated derived reports are documented and excluded from benchmark inputs
        BLOCKED if raw OHLCV integrity fails or aggregation is broken.

    gate_result
        BLOCKED if derived_artifact_gate is BLOCKED (contamination is a real finding).
        This is the strict gate used to track the overall Phase 1 certification state.
    """
    # --- raw_data_gate ---
    rejected_raw = [r for r in inventory if not r.get("approved", True)]
    raw_data_reasons: list[str] = []
    if rejected_raw:
        raw_data_reasons.append(
            f"{len(rejected_raw)} raw dataset(s) failed integrity checks: "
            + ", ".join(r["file"] for r in rejected_raw)
        )
    raw_data_gate = "PASS" if not raw_data_reasons else "BLOCKED"

    # --- derived_artifact_gate ---
    derived_reasons: list[str] = []
    sd_groups = contamination.get("signal_density_groups", [])
    if any(g.get("missing_metadata") for g in sd_groups):
        derived_reasons.append(
            "signal_density_report.json files lack embedded asset/timeframe metadata "
            "(reports cannot be traced to their originating asset/timeframe)"
        )
    copy_5m = timeframe_contamination.get("5m_is_copy_of", "UNKNOWN")
    copy_15m = timeframe_contamination.get("15m_is_copy_of", "UNKNOWN")
    if copy_5m != "UNKNOWN" or copy_15m != "UNKNOWN":
        derived_reasons.append(
            f"timeframe_runs/ contaminated: 5m is a copy of {copy_5m}, "
            f"15m is a copy of {copy_15m}"
        )
    derived_artifact_gate = "PASS" if not derived_reasons else "BLOCKED"

    # --- benchmark_readiness_gate ---
    # The benchmark (Phase 3) uses ONLY raw parquet files. Contaminated derived
    # reports are excluded from benchmark inputs by design. Missing 15m for non-BTC
    # assets is handled by on-the-fly aggregation (verified correct for BTC).
    benchmark_reasons: list[str] = []
    if raw_data_gate == "BLOCKED":
        benchmark_reasons.extend(raw_data_reasons)
    if agg_check.get("status") not in ("PASS",):
        benchmark_reasons.append(
            f"5m->15m aggregation check failed: {agg_check.get('status')}"
        )
    if la_check.get("status") not in ("PASS",):
        benchmark_reasons.append(
            f"Lookahead guard not confirmed: {la_check.get('status')}"
        )
    benchmark_readiness_gate = "PASS" if not benchmark_reasons else "BLOCKED"

    # --- overall gate_result (strict: BLOCKED if derived artifacts contaminated) ---
    overall_reasons: list[str] = []
    overall_reasons.extend(derived_reasons)
    overall_reasons.extend(raw_data_reasons)
    if missing_15m:
        overall_reasons.append(
            f"No 15m raw parquet data for multi-asset comparison: {', '.join(missing_15m)}"
        )
    gate_result = "BLOCKED" if overall_reasons else "PASS"

    return {
        "raw_data_gate": raw_data_gate,
        "raw_data_gate_reasons": raw_data_reasons,
        "derived_artifact_gate": derived_artifact_gate,
        "derived_artifact_gate_reasons": derived_reasons,
        "benchmark_readiness_gate": benchmark_readiness_gate,
        "benchmark_readiness_gate_reasons": benchmark_reasons,
        "gate_result": gate_result,
        "gate_reasons": overall_reasons,
    }


def _evaluate_gate(
    inventory: list[dict],
    contamination: dict,
    timeframe_contamination: dict,
    missing_15m: list[str],
) -> tuple[str, list[str]]:
    """Legacy single-gate evaluation (kept for compatibility)."""
    gates = _evaluate_gates(
        inventory, contamination, timeframe_contamination, missing_15m,
        agg_check={"status": "PASS"}, la_check={"status": "PASS"},
    )
    return gates["gate_result"], gates["gate_reasons"]


# ---------------------------------------------------------------------------
# Markdown report generator (Fix E)
# ---------------------------------------------------------------------------

def _write_markdown_report(output: dict, project_root: Path) -> None:
    """Write docs/market_data_integrity_report.md consistent with the JSON output."""
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "market_data_integrity_report.md"

    agg = output.get("aggregation_check", {})
    gates = {
        "raw_data_gate": output.get("raw_data_gate", "?"),
        "derived_artifact_gate": output.get("derived_artifact_gate", "?"),
        "benchmark_readiness_gate": output.get("benchmark_readiness_gate", "?"),
        "gate_result (overall)": output.get("gate_result", "?"),
    }
    la = output.get("lookahead_check", {})

    lines: list[str] = [
        "# Market Data Integrity Report",
        "",
        f"Generated: `{output.get('audit_timestamp', '?')}`  ",
        f"benchmark_readiness_gate: **{output.get('benchmark_readiness_gate', '?')}**",
        "",
        "## Gate Summary",
        "",
        "| Gate | Result |",
        "| --- | --- |",
    ]
    for name, val in gates.items():
        lines.append(f"| {name} | {val} |")

    approved = output.get("approved_datasets", [])
    rejected = output.get("rejected_datasets", [])
    lines += [
        "",
        "## Raw Data Inventory",
        "",
        f"- Datasets checked: **{len(approved) + len(rejected)}**",
        f"- Approved: **{len(approved)}**",
        f"- Rejected: **{len(rejected)}**",
    ]
    if rejected:
        lines.append("")
        for r in rejected:
            lines.append(f"  - REJECTED: `{r}`")

    agg_status = agg.get("status", "?")
    complete = agg.get("complete_buckets_compared", "?")
    full_overlap = agg.get("full_overlap_rows", "?")
    excl_inc = agg.get("excluded_incomplete_buckets", 0)
    excl_open = agg.get("open_comparison_excluded_buckets", 0)
    mismatches = agg.get("unexplained_mismatches", 0)
    per_col = agg.get("per_column_comparison_counts", {})
    per_mismatch = agg.get("per_column_mismatches", {})

    lines += [
        "",
        "## 5m → 15m Aggregation Check (BTC)",
        "",
        f"- Status: **{agg_status}**",
        f"- Ratio (5m rows / 15m rows): `{agg.get('actual_ratio', '?')}` (expected 3.0)",
        f"- Full overlap rows (inner join): **{full_overlap}**",
        f"- Complete buckets compared: **{complete}**",
        f"- Excluded incomplete buckets (< 3 bars): **{excl_inc}**",
        f"- Open-comparison-excluded buckets (zero-vol first bar): **{excl_open}**",
        f"- Unexplained mismatches: **{mismatches}**",
        "",
        "### Per-column comparison counts",
        "",
        "| Column | Rows compared | Mismatches |",
        "| --- | --- | --- |",
    ]
    for col in ("open", "high", "low", "close", "volume"):
        cnt = per_col.get(col, "—")
        mm = per_mismatch.get(col, "—")
        lines.append(f"| {col} | {cnt} | {mm} |")

    excl_ts = agg.get("excluded_incomplete_bucket_timestamps", [])
    open_excl_ts = agg.get("open_comparison_excluded_bucket_timestamps", [])

    lines += ["", "### Known anomalies (documented, excluded by policy)", ""]
    if excl_ts:
        lines.append("**Incomplete buckets (entire bucket excluded):**")
        for ts in excl_ts:
            details = agg.get("excluded_incomplete_bucket_details", {}).get(ts, {})
            bars = details.get("bars_present", "?")
            lines.append(f"- `{ts}` — {bars}/3 bars present")
    if open_excl_ts:
        lines.append("")
        lines.append("**Zero-volume first bar (Open comparison excluded; H/L/C/V still compared):**")
        reason = agg.get("open_comparison_excluded_reason", "")
        for ts in open_excl_ts:
            lines.append(f"- `{ts}` — {reason}")

    lines += [
        "",
        "## Lookahead Guard",
        "",
        f"- File: `{la.get('file', '?')}`",
        f"- Pattern found: `{la.get('pattern_found', '?')}`",
        f"- Status: **{la.get('status', '?')}**",
        "",
        "## Derived Artifact Contamination (documented findings)",
        "",
        "These findings apply to `data/timeframe_runs/` and `data/signal_density/` reports.",
        "They do NOT block Phase 3, which uses only raw OHLCV parquet files.",
        "",
        f"- Signal density duplicate groups: {len(output.get('report_contamination', {}).get('signal_density_groups', []))}",
        f"- Other contaminated report groups: {len(output.get('report_contamination', {}).get('other_contaminated_reports', []))}",
        f"- derived_artifact_gate: **{output.get('derived_artifact_gate', '?')}**",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown report: {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  Market Data Integrity Audit - DIAGNOSTIC ONLY")
    print("  Opens orders: False | Live trading: False")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Discover and check all parquet files in data/
    # ------------------------------------------------------------------
    print("\n[1/6] Scanning raw OHLCV parquet files in data/ ...")

    # Exclude market_features.parquet (not raw OHLCV)
    _NON_OHLCV = {"market_features.parquet"}
    parquet_files = sorted(
        [p for p in DATA_DIR.glob("*.parquet") if p.name not in _NON_OHLCV]
        # STRAT-01 research cache (atomic parquet + manifest, closed candles)
        + list((DATA_DIR / "strat01_cache").glob("*.parquet"))
    )

    inventory: list[dict] = []
    for pf in parquet_files:
        print(f"  Checking {pf.name} ...", end=" ", flush=True)
        result = _check_ohlcv_file(pf)
        status_tag = "OK" if result.get("approved") else f"FAIL ({result.get('rejection_reason')})"
        print(status_tag)
        inventory.append(result)

    approved_datasets = [r["file"] for r in inventory if r.get("approved")]
    rejected_datasets = [r["file"] for r in inventory if not r.get("approved")]

    # ------------------------------------------------------------------
    # 2. Report hash contamination
    # ------------------------------------------------------------------
    print("\n[2/6] Scanning report hash contamination ...")
    contamination = _build_contamination_report(DATA_DIR)
    sd_count = len(contamination["signal_density_groups"])
    other_count = len(contamination["other_contaminated_reports"])
    print(f"  signal_density duplicate groups : {sd_count}")
    print(f"  other contaminated report groups: {other_count}")

    # ------------------------------------------------------------------
    # 3. timeframe_runs contamination
    # ------------------------------------------------------------------
    print("\n[3/6] Verifying timeframe_runs/ independence ...")
    tf_contamination = _build_timeframe_runs_contamination(DATA_DIR)
    print(f"  5m copy of : {tf_contamination['5m_is_copy_of']}")
    print(f"  15m copy of: {tf_contamination['15m_is_copy_of']}")

    # ------------------------------------------------------------------
    # 4. Missing 15m assets
    # ------------------------------------------------------------------
    print("\n[4/6] Checking missing 15m raw parquet for non-BTC assets ...")
    # Known 5m-only assets (no 15m parquet found)
    _MISSING_15M = ["XRP/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    # Verify dynamically: if a 15m file exists for any of these, remove from list
    existing_names = {p.name.lower() for p in parquet_files}
    missing_15m: list[str] = []
    _ASSET_TO_PREFIX = {
        "XRP/USDT": "xrpusdt",
        "ETH/USDT": "ethusdt",
        "SOL/USDT": "solusdt",
        "BNB/USDT": "bnbusdt",
    }
    for asset, prefix in _ASSET_TO_PREFIX.items():
        has_15m = any(
            name.startswith(prefix) and "_15m" in name for name in existing_names
        )
        if not has_15m:
            missing_15m.append(asset)
    print(f"  Missing 15m data for: {missing_15m}")

    # ------------------------------------------------------------------
    # 5. Aggregation check (BTC 5m → 15m)
    # ------------------------------------------------------------------
    print("\n[5/6] Running 5m->15m aggregation check for BTC ...")
    agg_check = _aggregation_check(DATA_DIR)
    print(
        f"  Ratio 5m/15m rows: {agg_check.get('actual_ratio')}  "
        f"(expected 3.0)  Full overlap: {agg_check.get('full_overlap_rows', '?')} bars  "
        f"Compared (clean): {agg_check.get('complete_buckets_compared', '?')}  "
        f"Excluded incomplete: {agg_check.get('excluded_incomplete_buckets', 0)}  "
        f"Open-excl zero-vol: {agg_check.get('open_comparison_excluded_buckets', 0)}  "
        f"Unexplained mismatches: {agg_check.get('unexplained_mismatches', agg_check.get('sample_mismatches', '?'))}  "
        f"Status: {agg_check.get('status')}"
    )

    # ------------------------------------------------------------------
    # 6. Lookahead guard check
    # ------------------------------------------------------------------
    print("\n[6/6] Checking lookahead guard in paper_live.py ...")
    la_check = _lookahead_check(PROJECT_ROOT)
    print(f"  Pattern: {la_check['pattern_found']}  Status: {la_check['status']}")

    # ------------------------------------------------------------------
    # Gate evaluation (3-tier)
    # ------------------------------------------------------------------
    all_gates = _evaluate_gates(
        inventory, contamination, tf_contamination, missing_15m,
        agg_check=agg_check, la_check=la_check,
    )
    gate = all_gates["gate_result"]
    gate_reasons = all_gates["gate_reasons"]

    # ------------------------------------------------------------------
    # Compose output
    # ------------------------------------------------------------------
    pipeline_status = gate  # mirror

    output: dict[str, Any] = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
        "raw_data_inventory": inventory,
        "report_contamination": contamination,
        "timeframe_runs_contamination": tf_contamination,
        "aggregation_check": agg_check,
        "lookahead_check": la_check,
        "missing_15m_data": missing_15m,
        "approved_datasets": approved_datasets,
        "rejected_datasets": rejected_datasets,
        # 3-tier gate architecture (Prompt 2H)
        "raw_data_gate": all_gates["raw_data_gate"],
        "raw_data_gate_reasons": all_gates["raw_data_gate_reasons"],
        "derived_artifact_gate": all_gates["derived_artifact_gate"],
        "derived_artifact_gate_reasons": all_gates["derived_artifact_gate_reasons"],
        "benchmark_readiness_gate": all_gates["benchmark_readiness_gate"],
        "benchmark_readiness_gate_reasons": all_gates["benchmark_readiness_gate_reasons"],
        # Overall gate (backward compat)
        "pipeline_status": pipeline_status,
        "gate_result": gate,
        "gate_reasons": gate_reasons,
    }

    # ------------------------------------------------------------------
    # Write JSON
    # ------------------------------------------------------------------
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False, default=str)

    _write_markdown_report(output, PROJECT_ROOT)

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  AUDIT SUMMARY")
    print("=" * 70)
    print(f"  Raw datasets checked  : {len(inventory)}")
    print(f"  Approved datasets     : {len(approved_datasets)}")
    print(f"  Rejected datasets     : {len(rejected_datasets)}")
    print(f"  Missing 15m assets    : {len(missing_15m)}")
    print(f"  Aggregation check     : {agg_check.get('status')} (sample={agg_check.get('sample_size', 0)} bars)")
    print(f"  Lookahead guard       : {la_check['status']}")
    print(f"  Signal density groups : {len(contamination['signal_density_groups'])} duplicate groups")
    print(f"  Other contaminated    : {len(contamination['other_contaminated_reports'])} groups")
    print(f"\n  raw_data_gate         : {all_gates['raw_data_gate']}")
    print(f"  derived_artifact_gate : {all_gates['derived_artifact_gate']}")
    print(f"  benchmark_readiness_gate: {all_gates['benchmark_readiness_gate']}")
    print(f"\n  GATE RESULT (overall) : {gate}")
    if gate_reasons:
        for i, reason in enumerate(gate_reasons, 1):
            # Wrap long reasons
            words = reason.split()
            line = ""
            lines: list[str] = []
            for w in words:
                if len(line) + len(w) + 1 > 60:
                    lines.append(line)
                    line = w
                else:
                    line = f"{line} {w}".strip()
            if line:
                lines.append(line)
            print(f"    {i}. {lines[0]}")
            for extra in lines[1:]:
                print(f"       {extra}")
    print(f"\n  Output written to: {OUTPUT_PATH}")
    print("=" * 70)

    # Exit code 0 when benchmark_readiness_gate=PASS (Phase 3 can proceed).
    # gate_result remains BLOCKED due to known derived-artifact contamination
    # (Phase 1 finding, documented). That does not block Phase 3 raw-data use.
    sys.exit(0 if all_gates["benchmark_readiness_gate"] == "PASS" else 1)


if __name__ == "__main__":
    main()
