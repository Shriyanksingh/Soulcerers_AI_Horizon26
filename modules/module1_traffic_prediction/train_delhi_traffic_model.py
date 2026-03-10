from pathlib import Path

import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE1_DATA_DIR = PROJECT_ROOT / "data" / "module1"
MODULE1_MODELS_DIR = PROJECT_ROOT / "models" / "module1"


def resolve_delhi_files() -> tuple[Path, Path | None]:
    """Resolve Delhi traffic feature/target files from expected local folders."""
    feature_candidates = [
        MODULE1_DATA_DIR / "delhi" / "delhi_traffic_features.csv",
        PROJECT_ROOT / "delhi data" / "delhi_traffic_features.csv",
        PROJECT_ROOT / "delhi_data" / "delhi_traffic_features.csv",
    ]
    target_candidates = [
        MODULE1_DATA_DIR / "delhi" / "delhi_traffic_target.csv",
        PROJECT_ROOT / "delhi data" / "delhi_traffic_target.csv",
        PROJECT_ROOT / "delhi_data" / "delhi_traffic_target.csv",
    ]

    feature_path = None
    for path in feature_candidates:
        if path.exists():
            feature_path = path
            break
    if feature_path is None:
        raise FileNotFoundError(
            "delhi_traffic_features.csv not found in 'delhi data' or 'delhi_data'."
        )

    target_path = None
    for path in target_candidates:
        if path.exists():
            target_path = path
            break

    return feature_path, target_path


def normalize_traffic_level(value: str) -> str:
    """Normalize Delhi density labels to Low/Medium/High classes."""
    normalized = str(value).strip().lower()
    if normalized == "low":
        return "Low"
    if normalized == "medium":
        return "Medium"
    if normalized in {"high", "very high", "severe"}:
        return "High"
    raise ValueError(f"Unexpected traffic_density_level value: {value}")


def main() -> None:
    feature_path, target_path = resolve_delhi_files()
    df = pd.read_csv(feature_path)

    # Optional merge with travel-time file for future feature engineering.
    if target_path is not None:
        target_df = pd.read_csv(target_path)
        if {"Trip_ID", "travel_time_minutes"}.issubset(target_df.columns):
            df = df.merge(
                target_df[["Trip_ID", "travel_time_minutes"]],
                on="Trip_ID",
                how="left",
            )

    required_columns = {
        "start_area",
        "end_area",
        "distance_km",
        "time_of_day",
        "day_of_week",
        "weather_condition",
        "traffic_density_level",
        "road_type",
        "average_speed_kmph",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in Delhi features file: {sorted(missing)}")

    df = df.dropna(
        subset=[
            "start_area",
            "end_area",
            "distance_km",
            "time_of_day",
            "day_of_week",
            "weather_condition",
            "traffic_density_level",
            "road_type",
            "average_speed_kmph",
        ]
    ).copy()

    # Target for Delhi model: normalized traffic level class.
    df["traffic_level"] = df["traffic_density_level"].apply(normalize_traffic_level)

    feature_columns = [
        "start_area",
        "end_area",
        "distance_km",
        "time_of_day",
        "day_of_week",
        "weather_condition",
        "road_type",
        "average_speed_kmph",
    ]
    X = df[feature_columns].copy()
    y = df["traffic_level"].copy()

    categorical_features = [
        "start_area",
        "end_area",
        "time_of_day",
        "day_of_week",
        "weather_condition",
        "road_type",
    ]
    numeric_features = ["distance_km", "average_speed_kmph"]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_features,
            ),
            ("numeric", "passthrough", numeric_features),
        ]
    )

    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    random_state=42,
                    n_jobs=1,  # stable in restricted Windows environments
                ),
            ),
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    print(f"Delhi Traffic Model Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    labels = ["Low", "Medium", "High"]
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)
    print("\nConfusion Matrix:")
    print(cm_df)

    output_model_path = MODULE1_MODELS_DIR / "traffic_model_delhi.pkl"
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, output_model_path)
    print(f"\nSaved Delhi traffic model to: {output_model_path}")


if __name__ == "__main__":
    main()
