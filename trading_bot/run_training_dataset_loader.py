from core.training_dataset_loader import MultiAssetTrainingDatasetLoader


def main():
    df, report = MultiAssetTrainingDatasetLoader.load_expanded_training_dataset()
    print("[TrainingDatasetLoader] Completed")
    print(f"  Source rows : {report.total_rows_loaded}")
    print(f"  Train rows  : {report.rows_after_cleaning}")
    print(f"  Output      : {report.output_path}")
    print(f"  Assets      : {report.per_asset_counts}")
    print(f"  Regimes     : {report.per_regime_counts}")
    if report.warnings:
        print("  Warnings:")
        for w in report.warnings:
            print(f"    - {w}")


if __name__ == "__main__":
    main()
