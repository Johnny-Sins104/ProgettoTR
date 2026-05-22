import sys
import os
import argparse
import shutil
from pathlib import Path

import pandas as pd

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Use the repository root as working directory so data/ is always the same
# whether the script is launched as:
#   python trading_bot\\run_custom_backtest.py
# or from inside trading_bot:
#   python run_custom_backtest.py
TRADING_BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TRADING_BOT_DIR.parent
os.chdir(PROJECT_ROOT)

# Aggiunge trading_bot al path
sys.path.insert(0, str(TRADING_BOT_DIR))

from core.analyzer import TechnicalAnalyzer
from core.historical_cache import resolve_backtest_cache
from core.timeframe_profile import (
    apply_timeframe_profile,
    build_timeframe_profile,
    equivalent_rows_from_baseline_rows,
    parse_timeframe_list,
)
from core.runtime_profiler import RuntimeProfiler
import backtest_lab


def _asset_slug(symbol: str) -> str:
    return str(symbol).replace("/", "").replace(":", "").lower()

def _display_symbol(symbol: str) -> str:
    symbol = str(symbol).strip().upper().replace(":USDT", "")
    if "/" not in symbol and symbol.endswith("USDT"):
        symbol = symbol[:-4] + "/USDT"
    return symbol

def _load_and_validate_parquet(cache_path: str | os.PathLike[str]):
    from config import Config
    import polars as pl
    from core.data_collector import DatasetIntegrity

    print(f"📈 Caricamento dati da {cache_path}...")
    df_pl = pl.read_parquet(str(cache_path))

    # Validazione di sicurezza
    df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
    df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
    df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
    DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)

    df = df_pl.to_pandas()
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
        df = df.dropna(subset=["datetime"]).sort_values("datetime")
        df.set_index("datetime", inplace=True)
    else:
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df[~df.index.isna()].sort_index()
    return df


def main():
    parser = argparse.ArgumentParser(description="Simulatore di Backtest Personalizzato")
    parser.add_argument("--balance", type=float, default=100.0, help="Capitale iniziale in € (default: 100)")
    parser.add_argument("--candles", type=int, default=5000, help="Numero di candele recenti da testare (default: 5000)")
    parser.add_argument("--timeframe", type=str, default=None, help="Timeframe backtest: 15m, 5m o 3m. Default: Config.TIMEFRAME/env TIMEFRAME.")
    parser.add_argument("--symbol", type=str, default=None, help="Simbolo/asset da testare, es. BTC/USDT, ETH/USDT, SOL/USDT. Default: Config.SYMBOL/env SYMBOL.")
    parser.add_argument("--days", type=float, default=None, help="Durata temporale da testare. Se presente, sovrascrive --candles in base al timeframe.")
    parser.add_argument(
        "--equivalent-15m-candles",
        action="store_true",
        help="Interpreta --candles come profondità 15m equivalente. Esempio: 50000 -> 150000 su 5m, 250000 su 3m.",
    )
    parser.add_argument(
        "--compare-timeframes",
        type=str,
        default="",
        help="Lista comma-separated per audit manuale, es. 15m,5m,3m. Il runner esegue un timeframe per processo; questa opzione stampa i comandi equivalenti.",
    )
    parser.add_argument(
        "--no-scale-wf-to-timeframe",
        action="store_true",
        help="Non scala train/test/embargo quando si passa a 5m/3m. Utile solo per stress test rapidi.",
    )
    parser.add_argument(
        "--no-archive-timeframe-run",
        action="store_true",
        help="Non copiare i report finali in data/timeframe_runs/<timeframe>/ per confronto multi-timeframe.",
    )
    parser.add_argument(
        "--no-download-cache",
        action="store_true",
        help="Non scaricare dati mancanti: usa solo cache/dataset locali e avvisa se sono insufficienti.",
    )
    parser.add_argument(
        "--force-download-cache",
        action="store_true",
        help="Forza la ricostruzione/download della cache richiesta anche se esiste una cache locale.",
    )
    parser.add_argument("--fast", action="store_true", help="Modalità ricerca rapida: DYNAMIC-only, no charts, console WF ridotta.")
    parser.add_argument("--no-charts", action="store_true", help="Disabilita la generazione dei grafici HTML dei trade.")
    parser.add_argument(
        "--risk-profile",
        type=str,
        default=None,
        choices=["ALL", "LOW", "MEDIUM", "HIGH", "DYNAMIC"],
        help="Profilo rischio da simulare. Default: ALL; con --fast default DYNAMIC.",
    )
    parser.add_argument("--quiet-wf", action="store_true", help="Riduce stampa timeline/tabella fold walk-forward.")
    parser.add_argument(
        "--cost-model",
        type=str,
        default=None,
        choices=["base", "conservative", "severe"],
        help="Execution realism stress model. base=baseline, conservative=spread/slippage/latency stress, severe=stress massimo.",
    )
    args = parser.parse_args()

    from config import Config

    selected_symbol = _display_symbol(args.symbol or Config.SYMBOL)
    Config.SYMBOL = selected_symbol
    if args.cost_model:
        Config.EXECUTION_COST_MODEL = str(args.cost_model).lower()

    risk_profile = (args.risk_profile or ("DYNAMIC" if args.fast else "ALL")).upper()
    Config.BACKTEST_FAST_MODE = bool(args.fast)
    Config.BACKTEST_SAVE_CHARTS = not bool(args.no_charts or args.fast)
    Config.BACKTEST_RISK_PROFILE = risk_profile
    Config.BACKTEST_PRINT_WF_TIMELINE = not bool(args.quiet_wf or args.fast)
    Config.BACKTEST_PRINT_WF_FOLD_TABLE = not bool(args.quiet_wf or args.fast)
    Config.BACKTEST_PRINT_WF_MODEL_LINES = not bool(args.quiet_wf or args.fast)

    profiler = RuntimeProfiler(enabled=bool(getattr(Config, "RUNTIME_PROFILE_ENABLED", True)))
    Config.RUNTIME_PROFILER = profiler

    selected_timeframe = args.timeframe or Config.TIMEFRAME
    requested_rows = int(args.candles)
    if args.equivalent_15m_candles and args.days is None:
        requested_rows = equivalent_rows_from_baseline_rows(
            int(args.candles), baseline_timeframe="15m", target_timeframe=selected_timeframe
        )

    profile = build_timeframe_profile(
        config=Config,
        timeframe=selected_timeframe,
        requested_rows=requested_rows,
        days=args.days,
        scale_from_15m=not bool(args.no_scale_wf_to_timeframe),
    )
    apply_timeframe_profile(Config, profile)
    profiler.add_metadata(
        symbol=Config.SYMBOL,
        asset_slug=_asset_slug(Config.SYMBOL),
        timeframe=profile.timeframe,
        requested_rows=int(profile.requested_rows),
        approx_days=float(profile.approx_days),
        fast_mode=bool(args.fast),
        save_charts=bool(Config.BACKTEST_SAVE_CHARTS),
        risk_profile=Config.BACKTEST_RISK_PROFILE,
        cost_model=str(getattr(Config, "EXECUTION_COST_MODEL", "base")),
    )

    print(
        "🕒 [TimeframeProfile] "
        f"timeframe={profile.timeframe} | minutes={profile.minutes} | "
        f"requested_rows={profile.requested_rows} | approx_days={profile.approx_days:.1f} | "
        f"WF train/test/embargo/label={profile.wf_train_size}/{profile.wf_test_size}/{profile.embargo_gap}/{profile.wf_label_horizon} | "
        f"cost_stress={profile.cost_stress_multiplier:.2f}x"
    )
    for warning in profile.warnings:
        print(f"⚠️ [TimeframeProfile] {warning}")
    print(f"🪙 [AssetProfile] symbol={Config.SYMBOL} | asset_slug={_asset_slug(Config.SYMBOL)}")
    print(f"💸 [ExecutionCost] model={getattr(Config, 'EXECUTION_COST_MODEL', 'base')}")

    if args.compare_timeframes:
        # Running multiple full backtests inside one Python process would share global model/risk state.
        # Emit exact commands instead, then aggregate reports with run_timeframe_comparison.py.
        print("📋 [TimeframeComparison] Comandi equivalenti consigliati:")
        for tf in parse_timeframe_list(args.compare_timeframes):
            rows = int(args.candles)
            extra = ""
            if args.days is not None:
                extra = f" --days {args.days}"
            elif args.equivalent_15m_candles:
                rows = equivalent_rows_from_baseline_rows(int(args.candles), baseline_timeframe="15m", target_timeframe=tf)
            print(f"  python trading_bot\\run_custom_backtest.py --balance {args.balance:g} --symbol {Config.SYMBOL} --timeframe {tf} --candles {rows}{extra}")

    # Prompt 28.5/28.8: resolve the requested historical depth honestly per timeframe.
    with profiler.phase("cache_resolution_seconds"):
        resolution = resolve_backtest_cache(
            requested_rows=int(profile.requested_rows),
            config=Config,
            data_dir="data",
            allow_download=not bool(args.no_download_cache),
            force_download=bool(args.force_download_cache),
        )
    for warning in resolution.warnings:
        print(f"⚠️ [HistoricalCache] {warning}")
    if resolution.exact_or_sufficient:
        print(
            f"✅ [HistoricalCache] Cache satisfies request: "
            f"{resolution.rows} candles available for requested {resolution.requested_rows}."
        )
    else:
        print(
            f"⚠️ [HistoricalCache] Short-sample run: requested {resolution.requested_rows}, "
            f"available {resolution.rows}. Backtest results are not a {resolution.requested_rows}-candle test."
        )

    with profiler.phase("data_load_validate_seconds"):
        df = _load_and_validate_parquet(resolution.path)

    print("🔬 Calcolo degli indicatori tecnici avanzati...")
    with profiler.phase("indicator_seconds"):
        df = TechnicalAnalyzer().add_indicators(df)

    # Taglio alle ultime N candele solo se la cache è più capiente della richiesta.
    total_available = len(df)
    if profile.requested_rows < total_available:
        print(
            f"✂️ Taglio del grafico: considero solo le ultime {profile.requested_rows} "
            f"candele recenti su {total_available} totali."
        )
        df = df.iloc[-int(profile.requested_rows):]
    else:
        print(f"📊 Considero tutte le {total_available} candele disponibili.")

    if len(df) < int(profile.requested_rows):
        print(
            f"⚠️ [HistoricalCache] Requested {profile.requested_rows} candles but loaded only {len(df)}. "
            "Use --force-download-cache or verify data/datasets/candles_multi_asset.parquet."
        )

    # Configura il saldo iniziale
    backtest_lab.INITIAL_BALANCE = args.balance

    timeframe_min = int(profile.minutes)
    giorni = (len(df) * timeframe_min) / 60 / 24

    print("\n💰 ==================================================")
    print("  AVVIO SIMULAZIONE PERSONALIZZATA")
    print(f"  - Capitale Iniziale : {args.balance:.2f} €")
    print(f"  - Candele analizzate: {len(df)} (circa {giorni:.1f} giorni)")
    print("==================================================")

    # Manteniamo soglie diagnostiche permissive per analisi funnel/edge discovery;
    # il gating per archetipo e cost-aware resta responsabile della selettività.
    Config.META_PROB_THRESHOLD = 25.0
    Config.META_QUALITY_THRESHOLD = 25.0

    with profiler.phase("backtest_total_seconds"):
        backtest_lab.run_backtest(df)

    runtime_report = profiler.export(getattr(Config, "RUNTIME_PROFILE_REPORT_PATH", "data/runtime_profile_report.json"))

    if not bool(args.no_archive_timeframe_run):
        asset_slug = _asset_slug(Config.SYMBOL)
        cost_model_slug = str(getattr(Config, "EXECUTION_COST_MODEL", "base")).lower()
        archive_dir = Path("data") / "timeframe_runs" / profile.timeframe
        asset_archive_dir = Path("data") / "multi_asset_runs" / asset_slug / profile.timeframe
        asset_cost_archive_dir = asset_archive_dir / cost_model_slug
        archive_dir.mkdir(parents=True, exist_ok=True)
        asset_archive_dir.mkdir(parents=True, exist_ok=True)
        asset_cost_archive_dir.mkdir(parents=True, exist_ok=True)
        for name in [
            "paper_readiness_report.json",
            "signal_density_report.json",
            "archetype_performance_report.json",
            "monthly_performance_report.json",
            "equity_curve.csv",
            "lifecycle_consistency_report.json",
            "walkforward_audit_report.json",
        ]:
            src = Path("data") / name
            if src.exists():
                shutil.copy2(src, archive_dir / name)
                shutil.copy2(src, asset_archive_dir / name)
                shutil.copy2(src, asset_cost_archive_dir / name)
        runtime_src = Path("data") / "runtime_profile_report.json"
        if runtime_src.exists():
            shutil.copy2(runtime_src, archive_dir / "runtime_profile_report.json")
            shutil.copy2(runtime_src, asset_archive_dir / "runtime_profile_report.json")
            shutil.copy2(runtime_src, asset_cost_archive_dir / "runtime_profile_report.json")
        print(f"📦 [TimeframeProfile] Report archiviati in {archive_dir}")
        print(f"📦 [MultiAssetProfile] Report archiviati in {asset_archive_dir}")
        print(f"📦 [ExecutionCostProfile] Report archiviati in {asset_cost_archive_dir}")

    print("\n========================================================================================")
    print("  RUNTIME PROFILE")
    print("========================================================================================")
    for row in runtime_report.get("largest_phases", [])[:8]:
        print(f"  {row['phase']:<34}: {row['seconds']:.2f}s")
    print(f"  {'total_runtime_seconds':<34}: {runtime_report.get('total_runtime_seconds', 0.0):.2f}s")
    print(f"  [RuntimeProfile] Full report -> {getattr(Config, 'RUNTIME_PROFILE_REPORT_PATH', 'data/runtime_profile_report.json')}")


if __name__ == "__main__":
    main()
