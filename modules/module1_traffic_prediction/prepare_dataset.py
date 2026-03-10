from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE1_DATA_DIR = PROJECT_ROOT / "data" / "module1"


def resolve_input_file() -> Path:
    """Find the dataset in common local locations."""
    candidates = [
        MODULE1_DATA_DIR / "legacy_archive" / "Metro_Interstate_Traffic_Volume.csv",
        PROJECT_ROOT / "Metro_Interstate_Traffic_Volume.csv",
        PROJECT_ROOT / "archive (1)" / "Metro_Interstate_Traffic_Volume.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find Metro_Interstate_Traffic_Volume.csv in the current directory "
        "or in data/module1/legacy_archive."
    )


def main() -> None:
    # 1) Load the dataset
    input_path = resolve_input_file()
    df = pd.read_csv(input_path)

    # 2) Convert date_time to datetime
    df["date_time"] = pd.to_datetime(df["date_time"], errors="coerce")

    # Remove rows with invalid date_time values before creating time-based features.
    df = df.dropna(subset=["date_time"]).copy()

    # 3) Create time-based features
    df["hour"] = df["date_time"].dt.hour
    df["day_of_week"] = df["date_time"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # 4) Create traffic_level from traffic_volume
    conditions = [
        df["traffic_volume"] < 2000,
        df["traffic_volume"].between(2000, 4000, inclusive="both"),
        df["traffic_volume"] > 4000,
    ]
    choices = ["Low", "Medium", "High"]
    df["traffic_level"] = np.select(conditions, choices, default="Unknown")

    # 5) Keep only required columns for the final dataset
    final_columns = [
        "hour",
        "day_of_week",
        "weather_main",
        "temp",
        "rain_1h",
        "holiday",
        "traffic_level",
    ]
    processed_df = df[final_columns].copy()

    # 6) Save processed dataset
    output_path = MODULE1_DATA_DIR / "processed" / "traffic_dataset_processed.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed_df.to_csv(output_path, index=False)

    # 7) Print first 10 rows
    print(processed_df.head(10))


if __name__ == "__main__":
    main()
