from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE2_DATA_DIR = PROJECT_ROOT / "data" / "module2"
MODULE2_MODELS_DIR = PROJECT_ROOT / "models" / "module2"


def resolve_dataset_path() -> Path:
    """Find departure dataset in expected local locations."""
    candidates = [
        MODULE2_DATA_DIR / "departure_dataset.csv",
        PROJECT_ROOT / "departure_dataset.csv",
        PROJECT_ROOT / "archive (1)" / "departure_dataset.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "departure_dataset.csv not found. Generate it before training the model."
    )


def main() -> None:
    # 1) Load dataset
    dataset_path = resolve_dataset_path()
    df = pd.read_csv(dataset_path)
    df["day_of_week"] = df["day_of_week"].astype(str).str.strip().str.title()
    df["weather_main"] = df["weather_main"].astype(str).str.strip().str.title()
    df["holiday"] = df["holiday"].astype(str).str.strip().str.title()
    df["destination_type"] = df["destination_type"].astype(str).str.strip().str.lower()
    df["traffic_level"] = df["traffic_level"].astype(str).str.strip().str.title()

    # 2) Define features and target
    feature_columns = [
        "day_of_week",
        "weather_main",
        "temp",
        "rain_1h",
        "holiday",
        "destination_type",
        "preferred_arrival_hour",
        "traffic_level",
    ]
    target_column = "best_departure_hour"

    X = df[feature_columns].copy()
    y = df[target_column].copy()

    # 3) Preprocess categorical fields and passthrough numeric fields
    categorical_features = [
        "day_of_week",
        "weather_main",
        "holiday",
        "destination_type",
        "traffic_level",
    ]
    numeric_features = ["temp", "rain_1h", "preferred_arrival_hour"]

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

    # 4) Build model pipeline (preprocessing + regressor)
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=180,
                    max_depth=16,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=1,  # stable in restricted Windows environments
                ),
            ),
        ]
    )

    # 5) Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
    )

    # 6) Train model
    model.fit(X_train, y_train)

    # 7) Evaluate regression quality
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"Test MAE (hours): {mae:.3f}")
    print(f"Test R2: {r2:.4f}")

    # Optional hackathon metric: rounded-hour exact accuracy
    y_pred_hour = np.clip(np.rint(y_pred), 0, 23).astype(int)
    exact_hour_accuracy = (y_pred_hour == y_test.astype(int).to_numpy()).mean()
    print(f"Rounded Hour Accuracy: {exact_hour_accuracy:.4f}")

    # 8) Save full pipeline (includes preprocessing)
    output_model_path = MODULE2_MODELS_DIR / "departure_model.pkl"
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, output_model_path)
    print(f"Saved trained model to: {output_model_path}")


if __name__ == "__main__":
    main()
